/*
 * Copyright (C) 2026 Terento contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * This file is part of Terento.
 *
 * Terento is free software: you can redistribute it and/or modify it under
 * the terms of the GNU General Public License as published by the Free
 * Software Foundation, either version 3 of the License, or (at your option)
 * any later version.
 *
 * Terento is distributed in the hope that it will be useful, but WITHOUT
 * ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
 * FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License
 * for more details.
 *
 * You should have received a copy of the GNU General Public License along
 * with this program. If not, see <https://www.gnu.org/licenses/>.
 *
 * terento-preview-render renders a Garmin IMG map into Web Mercator
 * (EPSG:3857) WebP tiles for a bounding box and zoom range. It uses the
 * Garmin IMG decoder and renderer from GPXSee (GPL-3.0), vendored under
 * third_party/gpxsee.
 */

#include <cmath>
#include <cstdio>
#include <QByteArray>
#include <QDir>
#include <QElapsedTimer>
#include <QFileInfo>
#include <QGuiApplication>
#include <QImage>
#include <QImageWriter>
#include <QJsonDocument>
#include <QJsonObject>
#include <QAtomicInteger>
#include <QMutex>
#include <QPainter>
#include <QStringList>
#include <QThreadPool>
#include <QtConcurrent/QtConcurrentMap>
#include "map/IMG/imgdata.h"
#include "map/IMG/rastertile_img.h"
#include "map/IMG/style_img.h"
#include "map/pcs.h"
#include "map/projection.h"
#include "map/transform.h"
#include "common/wgs84.h"

using namespace IMG;

static const int TILE = 256;
static const double ORIGIN = M_PI * WGS84_RADIUS;

struct Options
{
	QStringList imgs;
	QString out;
	QString compareA, compareB;
	double minLon = 0, minLat = 0, maxLon = 0, maxLat = 0;
	int minZoom = 12, maxZoom = 16;
	int meta = 4;
	int quality = 78;
	int jobs = 1;
	bool hillShading = true;
	bool bboxSet = false;
	bool info = false;
};

static void usage()
{
	fprintf(stderr,
	  "usage: terento-preview-render --img FILE [--img OVERLAY]... (--info | --bbox W,S,E,N --out DIR)\n"
	  "  [--zoom MIN-MAX] [--meta N] [--quality Q] [--jobs N] [--no-hillshading]\n"
	  "       terento-preview-render --compare DIR_A DIR_B --zoom Z-Z\n");
}

static bool parse(const QStringList &args, Options &o)
{
	for (int i = 1; i < args.size(); i++) {
		const QString &a = args.at(i);
		QString v = (i + 1 < args.size()) ? args.at(i + 1) : QString();
		if (a == "--img") {o.imgs.append(v); i++;}
		else if (a == "--compare") {
			if (i + 2 >= args.size())
				return false;
			o.compareA = args.at(i + 1);
			o.compareB = args.at(i + 2);
			i += 2;
		}
		else if (a == "--out") {o.out = v; i++;}
		else if (a == "--info") o.info = true;
		else if (a == "--no-hillshading") o.hillShading = false;
		else if (a == "--meta") {o.meta = v.toInt(); i++;}
		else if (a == "--quality") {o.quality = v.toInt(); i++;}
		else if (a == "--jobs") {o.jobs = v.toInt(); i++;}
		else if (a == "--zoom") {
			QStringList z = v.split('-');
			if (z.size() != 2)
				return false;
			o.minZoom = z.at(0).toInt();
			o.maxZoom = z.at(1).toInt();
			i++;
		} else if (a == "--bbox") {
			QStringList b = v.split(',');
			if (b.size() != 4)
				return false;
			o.minLon = b.at(0).toDouble();
			o.minLat = b.at(1).toDouble();
			o.maxLon = b.at(2).toDouble();
			o.maxLat = b.at(3).toDouble();
			o.bboxSet = true;
			i++;
		} else
			return false;
	}
	if (!o.compareA.isEmpty())
		return o.imgs.isEmpty() && o.minZoom == o.maxZoom;
	if (o.imgs.isEmpty())
		return false;
	if (o.info)
		return true;
	return o.bboxSet && !o.out.isEmpty() && o.minLon < o.maxLon
	  && o.minLat < o.maxLat && o.minZoom >= 0 && o.minZoom <= o.maxZoom
	  && o.maxZoom <= 20 && o.meta >= 1 && o.meta <= 16 && o.quality >= 1
	  && o.quality <= 100 && o.jobs >= 1 && o.jobs <= 16;
}

static int lon2tile(double lon, int z)
{
	return qBound(0, (int)std::floor((lon + 180.0) / 360.0 * (1 << z)),
	  (1 << z) - 1);
}

static int lat2tile(double lat, int z)
{
	double r = lat * M_PI / 180.0;
	double t = (1.0 - std::log(std::tan(r) + 1.0 / std::cos(r)) / M_PI) / 2.0;
	return qBound(0, (int)std::floor(t * (1 << z)), (1 << z) - 1);
}

/* Mean absolute RGB difference (0-1) over the tiles both directories have
   at one zoom level; fully transparent pixels count as white paper. */
static int compare(const Options &o)
{
	const QString za(QString("%1/%2").arg(o.compareA).arg(o.minZoom));
	const QString zb(QString("%1/%2").arg(o.compareB).arg(o.minZoom));
	double sum = 0;
	qint64 pixels = 0, tiles = 0;

	const QStringList xs(QDir(za).entryList(QDir::Dirs | QDir::NoDotAndDotDot));
	for (int i = 0; i < xs.size(); i++) {
		const QStringList ys(QDir(za + "/" + xs.at(i)).entryList(
		  QStringList() << "*.webp", QDir::Files));
		for (int j = 0; j < ys.size(); j++) {
			const QString rel(xs.at(i) + "/" + ys.at(j));
			if (!QFileInfo::exists(zb + "/" + rel))
				continue;
			QImage a(QImage(za + "/" + rel).convertToFormat(QImage::Format_ARGB32));
			QImage b(QImage(zb + "/" + rel).convertToFormat(QImage::Format_ARGB32));
			if (a.isNull() || b.isNull() || a.size() != b.size())
				continue;
			for (int y = 0; y < a.height(); y++) {
				const QRgb *pa = (const QRgb*)a.constScanLine(y);
				const QRgb *pb = (const QRgb*)b.constScanLine(y);
				for (int x = 0; x < a.width(); x++) {
					QRgb ca = qAlpha(pa[x]) ? pa[x] : qRgb(255, 255, 255);
					QRgb cb = qAlpha(pb[x]) ? pb[x] : qRgb(255, 255, 255);
					sum += (qAbs(qRed(ca) - qRed(cb)) + qAbs(qGreen(ca)
					  - qGreen(cb)) + qAbs(qBlue(ca) - qBlue(cb))) / 765.0;
				}
			}
			pixels += (qint64)a.width() * a.height();
			tiles++;
		}
	}

	QJsonObject result;
	result["tiles"] = tiles;
	result["score"] = pixels ? sum / pixels : QJsonValue();
	printf("%s\n", QJsonDocument(result).toJson(QJsonDocument::Compact)
	  .constData());
	return 0;
}

int main(int argc, char *argv[])
{
	if (qEnvironmentVariableIsEmpty("QT_QPA_PLATFORM"))
		qputenv("QT_QPA_PLATFORM", "offscreen");
	QGuiApplication app(argc, argv);

	Options o;
	if (!parse(app.arguments(), o)) {
		usage();
		return 2;
	}

	if (!o.compareA.isEmpty())
		return compare(o);

	MapData::PolyCache polyCache;
	MapData::PointCache pointCache;
	MapData::ElevationCache demCache;
	QMutex lock, demLock;
	QList<IMGData*> layers;
	for (int i = 0; i < o.imgs.size(); i++) {
		IMGData *d = new IMGData(o.imgs.at(i), polyCache, pointCache, demCache,
		  lock, demLock);
		if (!d->isValid()) {
			fprintf(stderr, "error: %s: %s\n", qUtf8Printable(o.imgs.at(i)),
			  qUtf8Printable(d->errorString()));
			return 3;
		}
		layers.append(d);
	}
	/* The first map is the base; further maps (e.g. a contour add-on) are
	   drawn on top in the given order, each with its own TYP style. */
	IMGData &data = *layers.first();

	const RectC b(data.bounds());
	if (o.info) {
		QJsonObject info;
		info["name"] = data.name();
		info["bounds"] = QString("%1,%2,%3,%4").arg(b.left()).arg(b.bottom())
		  .arg(b.right()).arg(b.top());
		info["zoomMin"] = data.zooms().min();
		info["zoomMax"] = data.zooms().max();
		info["hasDEM"] = data.hasDEM();
		info["hasTYP"] = data.typ() != 0;
		printf("%s\n", QJsonDocument(info).toJson(QJsonDocument::Compact)
		  .constData());
		return 0;
	}

	QList<Style*> styles;
	for (int i = 0; i < layers.size(); i++)
		styles.append(new Style(1.0, layers.at(i)->typ()));
	Projection proj(PCS::pcs(3857));
	const bool hillShading = o.hillShading && data.hasDEM();

	/* One job per metatile, run on --jobs threads. The IMG data caches are
	   shared and guarded by the locks passed to IMGData, as in GPXSee. */
	struct Job {int z, mx, my, w, h;};
	QList<Job> jobs;
	for (int z = o.minZoom; z <= o.maxZoom; z++) {
		const int x0 = lon2tile(o.minLon, z), x1 = lon2tile(o.maxLon, z);
		const int y0 = lat2tile(o.maxLat, z), y1 = lat2tile(o.minLat, z);
		for (int mx = x0; mx <= x1; mx += o.meta)
			for (int my = y0; my <= y1; my += o.meta)
				jobs.append({z, mx, my, qMin(o.meta, x1 - mx + 1),
				  qMin(o.meta, y1 - my + 1)});
	}

	QElapsedTimer timer;
	timer.start();
	QAtomicInteger<qint64> tiles(0), bytes(0);
	QAtomicInt failure(0);
	QMutex errorLock;
	QString error;

	auto render = [&](const Job &job) {
		if (failure.loadRelaxed())
			return;
		const double scale = (2.0 * ORIGIN) / ((double)TILE * (1 << job.z));
		const Transform transform(ReferencePoint(PointD(0, 0),
		  PointD(-ORIGIN, ORIGIN)), PointD(scale, scale));
		/* GPXSee IMG zoom n means 2^n tiles of 1 px; slippy zoom z with
		   256 px tiles is n = z + 8. Data level selection is clamped to
		   the levels the map provides. */
		const int zoom = job.z + 8;
		const QRect rect(job.mx * TILE, job.my * TILE, job.w * TILE,
		  job.h * TILE);
		QImage img(rect.size(), QImage::Format_ARGB32_Premultiplied);
		/* Paper colour under every style: BBBike and MapRando maps have no
		   land fill and would otherwise leave transparent tiles. */
		img.fill(Qt::white);
		QPainter painter(&img);
		for (int n = 0; n < layers.size(); n++) {
			IMGData *d = layers.at(n);
			RasterTile tile(&proj, transform, d, styles.at(n),
			  qBound(d->zooms().min(), zoom, d->zooms().max()), rect,
			  1.0, n == 0 && hillShading, true, true);
			tile.render();
			painter.drawPixmap(0, 0, tile.pixmap());
		}
		painter.end();

		for (int i = 0; i < job.w; i++) {
			const QString dir(QString("%1/%2/%3").arg(o.out).arg(job.z)
			  .arg(job.mx + i));
			if (!QDir().mkpath(dir)) {
				QMutexLocker locker(&errorLock);
				error = QString("cannot create %1").arg(dir);
				failure.storeRelaxed(4);
				return;
			}
			for (int j = 0; j < job.h; j++) {
				const QString path(QString("%1/%2.webp").arg(dir)
				  .arg(job.my + j));
				QImage t(img.copy(i * TILE, j * TILE, TILE, TILE));
				QImageWriter writer(path, "webp");
				writer.setQuality(o.quality);
				if (!writer.write(t)) {
					QMutexLocker locker(&errorLock);
					error = QString("%1: %2").arg(path, writer.errorString());
					failure.storeRelaxed(5);
					return;
				}
				tiles.fetchAndAddRelaxed(1);
				bytes.fetchAndAddRelaxed(QFileInfo(path).size());
			}
		}
	};

	QThreadPool pool;
	pool.setMaxThreadCount(o.jobs);
	QtConcurrent::blockingMap(&pool, jobs, render);
	if (failure.loadRelaxed()) {
		fprintf(stderr, "error: %s\n", qUtf8Printable(error));
		return failure.loadRelaxed();
	}

	QJsonObject result;
	result["tiles"] = tiles.loadRelaxed();
	result["bytes"] = bytes.loadRelaxed();
	result["seconds"] = timer.elapsed() / 1000.0;
	result["hillShading"] = hillShading;
	printf("%s\n", QJsonDocument(result).toJson(QJsonDocument::Compact)
	  .constData());

	qDeleteAll(styles);
	qDeleteAll(layers);

	return 0;
}
