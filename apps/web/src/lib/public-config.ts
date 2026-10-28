// Settings the browser needs, read from the server's environment when a page is rendered
// rather than inlined at build time (as NEXT_PUBLIC_* variables would be), so the same image
// can point at any Supabase project.

export type PublicConfig = {
  supabaseUrl: string | null;
  supabaseAnonKey: string | null;
};

export function readPublicConfig(): PublicConfig {
  return {
    supabaseUrl: process.env.SUPABASE_URL || null,
    supabaseAnonKey: process.env.SUPABASE_ANON_KEY || null,
  };
}
