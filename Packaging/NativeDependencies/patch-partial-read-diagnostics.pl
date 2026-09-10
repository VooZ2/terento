#!/usr/bin/perl
use strict;
use warnings;

# libmtp 1.1.23 discards the native PTP response for a failed partial read.
# Preserve it in the existing error stack without changing the transaction.
my $path = shift @ARGV or die "Expected libmtp.c path\n";
open my $input, '<', $path or die "$path: $!\n";
local $/;
my $source = <$input>;
close $input;
my $original = <<'SOURCE';
    ret = ptp_android_getpartialobject64(params, id, offset, maxbytes, data, size);
  }
  if (ret == PTP_RC_OK)
      return 0;
  return -1;
SOURCE
my $replacement = $original;
$replacement =~ s/  return -1;/  add_ptp_error_to_errorstack(device, ret, "Terento partial read response");\n  return -1;/;
my $original_count = () = $source =~ /\Q$original\E/g;
my $patched_count = () = $source =~ /\Q$replacement\E/g;
if ($original_count == 0 && $patched_count == 1) {
    print "Partial-read PTP diagnostics patch already applied\n";
    exit 0;
}
die "Pinned partial-read source does not match exactly\n"
    unless $original_count == 1 && $patched_count == 0;
$source =~ s/\Q$original\E/$replacement/;
open my $output, '>', $path or die "$path: $!\n";
print {$output} $source;
close $output or die "$path: $!\n";
print "Partial-read PTP diagnostics patch applied\n";
