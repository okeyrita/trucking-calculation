import { useEffect } from 'react'
import { MapContainer, Marker, Polyline, Popup, TileLayer, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { FuelStop } from '../types'

// Leaflet's default marker icons are resolved relative to the CSS, which breaks
// under a bundler. Numbered divIcons are clearer here anyway: the number is the
// order the driver fuels in.
function stopIcon(seq: number) {
  return L.divIcon({
    className: 'stop-pin',
    html: `<span>${seq}</span>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  })
}

const endpointIcon = (kind: 'start' | 'end') =>
  L.divIcon({
    className: `endpoint-pin endpoint-${kind}`,
    html: `<span>${kind === 'start' ? 'A' : 'B'}</span>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  })

function FitBounds({ positions }: { positions: [number, number][] }) {
  const map = useMap()
  useEffect(() => {
    if (positions.length > 1) {
      map.fitBounds(L.latLngBounds(positions), { padding: [30, 30] })
    }
  }, [map, positions])
  return null
}

interface Props {
  /** GeoJSON coordinates, i.e. [lon, lat] — flipped here for Leaflet. */
  geometry: [number, number][]
  stops: FuelStop[]
  currency: (value: number) => string
}

export function RouteMap({ geometry, stops, currency }: Props) {
  const line: [number, number][] = geometry.map(([lon, lat]) => [lat, lon])
  const start = line[0]
  const end = line[line.length - 1]

  return (
    <MapContainer center={start ?? [39.5, -98]} zoom={5} className="map" scrollWheelZoom>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <Polyline positions={line} pathOptions={{ color: '#2563eb', weight: 4, opacity: 0.85 }} />
      {start && <Marker position={start} icon={endpointIcon('start')} />}
      {end && <Marker position={end} icon={endpointIcon('end')} />}
      {stops
        .filter((stop) => stop.lat != null && stop.lon != null)
        .map((stop) => (
          <Marker
            key={stop.seq}
            position={[stop.lat as number, stop.lon as number]}
            icon={stopIcon(stop.seq)}
          >
            <Popup>
              <strong>{stop.name}</strong>
              <br />
              {stop.state} · mile {Math.round(stop.mile_marker)}
              <br />
              {stop.gallons.toFixed(0)} gal @ {currency(stop.price_per_gallon)}/gal
              <br />
              {currency(stop.cost)}
            </Popup>
          </Marker>
        ))}
      <FitBounds positions={line} />
    </MapContainer>
  )
}
