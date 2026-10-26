# Landing page video sources

This directory contains the editable HyperFrames compositions used for the
landing page videos:

- `workspace-overview/` — Workspace Overview composition
- `data-lineage/` — Data Lineage composition

Each project pins HyperFrames `0.8.198` in its npm scripts. Run `npm run check`
or `npm run render` from either project directory to validate or render it.

The landing page serves optimized MP4 and WebM files from
`my-dash-app/assets/animations/`. Those tracked files are the delivery copies;
the 1080p working renders and HyperFrames capture artifacts are not duplicated
here. The poster images in the app assets are the same as the generated
composition posters.
