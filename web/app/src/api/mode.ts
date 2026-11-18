/// Chosen at build time. The default, `local`, runs the Python engine in the browser (Pyodide, no backend);
/// `VITE_API_MODE=http` sends the same requests to a server at VITE_API_BASE instead.
export const API_MODE: 'http' | 'local' = (import.meta.env.VITE_API_MODE as string | undefined) === 'http' ? 'http' : 'local'
export const IS_LOCAL = API_MODE === 'local'
