#!/usr/bin/perl
use strict;
use warnings;

# Narrow Darwin workaround and deterministic handle cleanup for pinned libmtp
# 1.1.23. Do not modify PTP reads, explicit error recovery, or other device flags.
my $path = shift @ARGV or die "Expected libusb1-glue.c path\n";
open my $input, '<', $path or die "$path: $!\n";
local $/;
my $source = <$input>;
close $input;

sub replace_exact {
    my ($before, $after, $expected) = @_;
    my $remaining = $source;
    my $patched_count = $remaining =~ s/\Q$after\E//g;
    my $original_count = () = $remaining =~ /\Q$before\E/g;
    return if $original_count == 0 && $patched_count == $expected;
    die "Pinned USB session source does not match exactly\n"
        unless $original_count == $expected && $patched_count == 0;
    $source =~ s/\Q$before\E/$after/g;
}

my $close_before = <<'SOURCE';
static void close_usb(PTP_USB* ptp_usb)
SOURCE
my $close_after = <<'SOURCE';
/* Terento local candidate: avoid flag-driven USB re-enumeration on close
 * for macOS VID/PID 091e:51b8 only; hardware retest is required. Other quirks
 * and the explicit failed-open recovery reset remain unchanged. */
static int terento_force_reset_on_close(PTP_USB *ptp_usb)
{
#ifdef __APPLE__
  if (ptp_usb->rawdevice.device_entry.vendor_id == 0x091e &&
      ptp_usb->rawdevice.device_entry.product_id == 0x51b8)
    return 0;
#endif
  return FLAG_FORCE_RESET_ON_CLOSE(ptp_usb);
}

static void close_usb(PTP_USB* ptp_usb)
SOURCE
replace_exact($close_before, $close_after, 1);
replace_exact("  if (FLAG_FORCE_RESET_ON_CLOSE(ptp_usb)) {\n",
              "  if (terento_force_reset_on_close(ptp_usb)) {\n", 1);
replace_exact("  libusb_close(ptp_usb->handle);\n}\n",
              "  libusb_close(ptp_usb->handle);\n  ptp_usb->handle = NULL;\n}\n", 1);

# init_ptp_usb owns the handle from libusb_open until success. Its caller
# cannot safely release an interface that failed to claim.
replace_exact("  ret = libusb_open(dev, &device_handle);\n",
              "  ptp_usb->handle = NULL;\n  ret = libusb_open(dev, &device_handle);\n", 1);
my $descriptor_before = <<'SOURCE';
      perror("libusb_get_active_config_descriptor(2) failed");
      return -1;
SOURCE
my $descriptor_after = <<'SOURCE';
      perror("libusb_get_active_config_descriptor(2) failed");
      libusb_close(ptp_usb->handle);
      ptp_usb->handle = NULL;
      return -1;
SOURCE
replace_exact($descriptor_before, $descriptor_after, 2);
my $claim_before = <<'SOURCE';
      fprintf(stderr, "error returned by libusb_claim_interface() = %d", usbresult);
    return -1;
SOURCE
my $claim_after = <<'SOURCE';
      fprintf(stderr, "error returned by libusb_claim_interface() = %d", usbresult);
    libusb_free_config_descriptor(config);
    libusb_close(ptp_usb->handle);
    ptp_usb->handle = NULL;
    return -1;
SOURCE
replace_exact($claim_before, $claim_after, 1);

# These failures occur after successful init/claim. Close without a second
# reset or endpoint requests against an already failed session.
my $retry_before = <<'SOURCE';
      LIBMTP_ERROR("LIBMTP PANIC: failed to open session on second attempt\n");
      libusb_free_device_list (devs, 0);
SOURCE
my $retry_after = <<'SOURCE';
      LIBMTP_ERROR("LIBMTP PANIC: failed to open session on second attempt\n");
      libusb_release_interface(ptp_usb->handle, ptp_usb->interface);
      libusb_close(ptp_usb->handle);
      ptp_usb->handle = NULL;
      libusb_free_device_list (devs, 0);
SOURCE
replace_exact($retry_before, $retry_after, 1);
my $session_before = <<'SOURCE';
    libusb_release_interface(ptp_usb->handle, ptp_usb->interface);
    libusb_free_device_list (devs, 0);
SOURCE
my $session_after = <<'SOURCE';
    libusb_release_interface(ptp_usb->handle, ptp_usb->interface);
    libusb_close(ptp_usb->handle);
    ptp_usb->handle = NULL;
    libusb_free_device_list (devs, 0);
SOURCE
replace_exact($session_before, $session_after, 1);

open my $output, '>', $path or die "$path: $!\n";
print {$output} $source;
close $output or die "$path: $!\n";
print "USB session lifecycle patch applied or already present\n";
