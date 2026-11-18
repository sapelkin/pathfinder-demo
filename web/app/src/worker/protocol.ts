// Messages between the main thread and the engine worker.
export type WorkerRequest =
  | { type: 'init'; baseURL: string; document: string | null }
  | { type: 'call'; id: number; method: 'GET' | 'POST'; path: string; query: Record<string, string>; body: unknown }
  | { type: 'export'; id: number }
  | { type: 'import'; id: number; text: string }

export type WorkerResponse =
  | { type: 'progress'; stage: string; loaded?: number; total?: number }
  | { type: 'ready'; engine: string; stubDispatch: boolean; restored: boolean }
  | { type: 'fatal'; message: string }
  | { type: 'result'; id: number; status: number; body: unknown }
  | { type: 'exported'; id: number; text: string }
  | { type: 'imported'; id: number; ok: boolean; error?: string }
  | { type: 'document'; text: string }
