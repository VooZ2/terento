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
#include <QMutex>
#include <QPainter>
#include <QStringList>
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
	QString img;
	QString out;
	double minLon = 0, minLat = 0, maxLon = 0, maxLat = 0;
	int minZoom = 12, maxZoom = 16;
	int meta = 4;
	int quality = 78;
	bool hillShading = true;
	bool bboxSet = false;
	bool info = false;
};

static void usage()
{
	fprintf(stderr,
	  "usage: terento-preview-render --img FILE (--info | --bbox W,S,E,N --out DIR)\n"
	  "  [--zoom MIN-MAX] [--meta N] [--quality Q] [--no-hillshading]\n");
}

static bool parse(const QStringList &args, Options &o)
{
	for (int i = 1; i < args.size(); i++) {
		const QString &a = args.at(i);
		QString v = (i + 1 < args.size()) ? args.at(i + 1) : QString();
		if (a == "--img") {o.img = v; i++;}
		else if (a == "--out") {o.out = v; i++;}
		else if (a == "--info") o.info = true;
		else if (a == "--no-hillshading") o.hillShading = false;
		else if (a == "--meta") {o.meta = v.toInt(); i++;}
		else if (a == "--quality") {o.quality = v.toInt(); i++;}
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
	if (o.img.isEmpty())
		return false;
	if (o.info)
		return true;
	return o.bboxSet && !o.out.isEmpty() && o.minLon < o.maxLon
	  && o.minLat < o.maxLat && o.minZoom >= 0 && o.minZoom <= o.maxZoom
	  && o.maxZoom <= 20 && o.meta >= 1 && o.meta <= 16 && o.quality >= 1
	  && o.quality <= 100;
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

	MapData::PolyCache polyCache;
	MapData::PointCache pointCache;
	MapData::ElevationCache demCache;
	QMutex lock, demLock;
	IMGData data(o.img, polyCache, pointCache, demCache, lock, demLock);
	if (!data.isValid()) {
		fprintf(stderr, "error: %s\n", qUtf8Printable(data.errorString()));
		return 3;
	}

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

	Style style(1.0, data.typ());
	Projection proj(PCS::pcs(3857));
	const bool hillShading = o.hillShading && data.hasDEM();

	QElapsedTimer timer;
	timer.start();
	qint64 tiles = 0, bytes = 0;

	for (int z = o.minZoom; z <= o.maxZoom; z++) {
		const int x0 = lon2tile(o.minLon, z), x1 = lon2tile(o.maxLon, z);
		const int y0 = lat2tile(o.maxLat, z), y1 = lat2tile(o.minLat, z);
		const double scale = (2.0 * ORIGIN) / ((double)TILE * (1 << z));
		const Transform transform(ReferencePoint(PointD(0, 0),
		  PointD(-ORIGIN, ORIGIN)), PointD(scale, scale));
		/* GPXSee IMG zoom n means 2^n tiles of 1 px; slippy zoom z with
		   256 px tiles is n = z + 8. Data level selection is clamped to
		   the levels the map provides. */
		const int imgZoom = qBound(data.zooms().min(), z + 8,
		  data.zooms().max());

		for (int mx = x0; mx <= x1; mx += o.meta) {
			for (int my = y0; my <= y1; my += o.meta) {
				const int w = qMin(o.meta, x1 - mx + 1);
				const int h = qMin(o.meta, y1 - my + 1);
				RasterTile tile(&proj, transform, &data, &style, imgZoom,
				  QRect(mx * TILE, my * TILE, w * TILE, h * TILE), 1.0,
				  hillShading, true, true);
				tile.render();
				const QImage img(tile.pixmap().toImage());

				for (int i = 0; i < w; i++) {
					for (int j = 0; j < h; j++) {
						const QString dir(QString("%1/%2/%3").arg(o.out)
						  .arg(z).arg(mx + i));
						if (!QDir().mkpath(dir)) {
							fprintf(stderr, "error: cannot create %s\n",
							  qUtf8Printable(dir));
							return 4;
						}
						const QString path(QString("%1/%2.webp").arg(dir)
						  .arg(my + j));
						QImage t(img.copy(i * TILE, j * TILE, TILE, TILE));
						QImageWriter writer(path, "webp");
						writer.setQuality(o.quality);
						if (!writer.write(t)) {
							fprintf(stderr, "error: %s: %s\n",
							  qUtf8Printable(path),
							  qUtf8Printable(writer.errorString()));
							return 5;
						}
						tiles++;
						bytes += QFileInfo(path).size();
					}
				}
			}
		}
	}

	QJsonObject result;
	result["tiles"] = tiles;
	result["bytes"] = bytes;
	result["seconds"] = timer.elapsed() / 1000.0;
	result["hillShading"] = hillShading;
	printf("%s\n", QJsonDocument(result).toJson(QJsonDocument::Compact)
	  .constData());

	return 0;
}
