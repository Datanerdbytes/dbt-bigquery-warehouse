import { build } from "esbuild";
await build({
  entryPoints: ["my-dash-app/auth_frontend/main.js"],
  outfile: "my-dash-app/assets/auth.bundle.js",
  bundle: true,
  minify: true,
  sourcemap: false,
  target: ["es2020"],
  // Keep string whitespace escaped so Git whitespace hooks preserve its value.
  supported: { "template-literal": false },
  define: {
    "process.env.NEXT_PUBLIC_SUPABASE_URL": JSON.stringify(
      process.env.NEXT_PUBLIC_SUPABASE_URL || "",
    ),
    "process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY": JSON.stringify(
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "",
    ),
  },
});

await build({
  entryPoints: ["my-dash-app/auth_frontend/showcase.js"],
  outfile: "my-dash-app/assets/showcase.bundle.js",
  bundle: true,
  minify: true,
  sourcemap: false,
  target: ["es2020"],
  // Keep string whitespace escaped so Git whitespace hooks preserve its value.
  supported: { "template-literal": false },
});
