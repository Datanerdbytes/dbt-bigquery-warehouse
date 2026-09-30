import { build } from "esbuild";
await build({
  entryPoints: ["my-dash-app/auth_frontend/main.js"],
  outfile: "my-dash-app/assets/auth.bundle.js",
  bundle: true,
  minify: true,
  sourcemap: false,
  target: ["es2020"],
  define: {
    "process.env.NEXT_PUBLIC_SUPABASE_URL": JSON.stringify(
      process.env.NEXT_PUBLIC_SUPABASE_URL || "",
    ),
    "process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY": JSON.stringify(
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "",
    ),
  },
});
