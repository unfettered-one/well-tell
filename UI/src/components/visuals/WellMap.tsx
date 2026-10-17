import { useState } from 'react'
import { MapContainer, CircleMarker, Popup, TileLayer } from 'react-leaflet'
import type { LatLngBoundsExpression } from 'leaflet'
import type { Visual } from '../../contracts'
import { fieldsFor, fieldTitle, formatValue, isNumber } from './format'
import 'leaflet/dist/leaflet.css'

export default function WellMap({ visual }: { visual: Visual }) {
  const [tileError, setTileError] = useState(false)
  const { latitude, longitude } = visual
  if (!latitude || !longitude)
    throw new Error('Explicit latitude and longitude mappings were not supplied.')
  const valid = visual.data.filter(
    (d) =>
      isNumber(d[latitude]) &&
      isNumber(d[longitude]) &&
      Math.abs(d[latitude]) <= 90 &&
      Math.abs(d[longitude]) <= 180,
  )
  if (!valid.length)
    throw new Error('No valid coordinates were returned. No locations have been invented.')
  const bounds = valid.map((d) => [
    d[latitude] as number,
    d[longitude] as number,
  ]) as LatLngBoundsExpression
  return (
    <div>
      {valid.length !== visual.data.length && (
        <p className="visual-warning">
          {visual.data.length - valid.length} row(s) have missing or invalid coordinates and are not
          placed on the map. See returned data below.
        </p>
      )}
      {tileError && (
        <p className="visual-warning" role="status">
          Map tiles are unavailable. Returned well markers and their details remain available; use
          the data table if the map is unreadable.
        </p>
      )}
      <div className="well-map" role="region" aria-label="Well locations">
        <MapContainer
          bounds={bounds}
          boundsOptions={{ padding: [32, 32], maxZoom: 12 }}
          scrollWheelZoom={false}
        >
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            eventHandlers={{ tileerror: () => setTileError(true) }}
          />
          {valid.map((d, i) => (
            <CircleMarker
              key={i}
              center={[d[latitude] as number, d[longitude] as number]}
              radius={8}
              pathOptions={{ color: '#fff', weight: 2, fillColor: '#237965', fillOpacity: 0.95 }}
              bubblingMouseEvents={false}
            >
              <Popup>
                <div className="map-popup">
                  <strong>
                    {formatValue(d[visual.well_id || 'asset_id'] ?? 'Returned location')}
                  </strong>
                  <dl>
                    {fieldsFor(visual.data, visual.columns).map((f) => (
                      <div key={f.field}>
                        <dt>{fieldTitle(f)}</dt>
                        <dd>{formatValue(d[f.field], f)}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              </Popup>
            </CircleMarker>
          ))}
        </MapContainer>
      </div>
      <p className="chart-caption">
        {valid.length} returned location(s). Select a marker for details. Overlapping locations may
        share a marker position.
      </p>
    </div>
  )
}
