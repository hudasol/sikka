# ADR 0006: MapLibre with local GeoJSON and no base map tiles

Status: accepted

## Context

Maps help a reviewer see where flagged crashes and ranked segments are. Tile providers are either paid, rate limited, or would add third party network requests and tracking. The network is synthetic and placed on an invented grid, so a real base map would also suggest a correspondence with real roads that does not exist.

## Decision

Maps use MapLibre GL with a style that has a plain background layer and only GeoJSON sources served by Sikka itself (the synthetic network and the points being shown). The style declares no glyphs and no sprites, so no fonts or icons are fetched. MapLibre is loaded lazily, only on screens that show a map, and every map has a table alternative.

## Consequences

- No network requests leave the product; the end to end tests assert this for every screen.
- Without a base map the geography is abstract, which is honest for synthetic data.
- Labels on the map are not drawn; the table alternative and the detail panels carry names and identifiers.
