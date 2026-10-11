# World geometry

`world_110m.json` is Plotly's world geometry, downloaded from
https://cdn.plot.ly/world_110m.json on 2026-10-11. The same asset is distributed
in https://github.com/plotly/plotly.js/tree/master/dist/topojson.

It contains Natural Earth public-domain geographic data. Serving this static
asset from the app lets the revenue map render with the existing same-origin
Content Security Policy and without a runtime CDN connection. Keep the graph's
`topojsonURL` directory and default 110m world resolution consistent with it.
