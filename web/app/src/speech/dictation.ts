// Dictation through Azure AI Speech (en-AU). The browser never holds the Speech key: it asks the API for a short-lived
// authorization token (GET /speech/token). A VITE_SPEECH_KEY still works for local development. When neither is
// available the microphone button says so and typing works.
import { api } from '../api/client'

export const SPEECH_KEY = (import.meta.env.VITE_SPEECH_KEY as string | undefined) || ''
export const SPEECH_REGION = (import.meta.env.VITE_SPEECH_REGION as string | undefined) || ''
export const SPEECH_TOKEN_OFF = (import.meta.env.VITE_SPEECH_TOKEN as string | undefined) === '0'
export const speechConfigured = Boolean(SPEECH_KEY && SPEECH_REGION) || !SPEECH_TOKEN_OFF
export const SPEECH_OFF_STATUS = 'Dictation is off in this build: no speech key is configured. Type the note instead.'

type Recognizer = { stopContinuousRecognitionAsync: (ok?: () => void, err?: (e: string) => void) => void; close: () => void }

export class Dictation {
  private recognizer: Recognizer | null = null
  private base = ''
  private partial = ''
  private finals: string[] = []
  onText: (text: string) => void = () => {}
  onStatus: (status: string) => void = () => {}
  onListening: (listening: boolean) => void = () => {}

  get isListening(): boolean { return this.recognizer !== null }

  async start(continuing: string): Promise<void> {
    if (!speechConfigured) { this.onStatus(SPEECH_OFF_STATUS); return }
    if (this.recognizer) return
    this.base = continuing
    this.finals = []
    this.partial = ''
    try {
      const sdk = await import('microsoft-cognitiveservices-speech-sdk')
      let cfg
      if (SPEECH_KEY && SPEECH_REGION) {
        cfg = sdk.SpeechConfig.fromSubscription(SPEECH_KEY, SPEECH_REGION)
      } else {
        const t = await api.speechToken()
        cfg = sdk.SpeechConfig.fromAuthorizationToken(t.token, t.region)
      }
      cfg.speechRecognitionLanguage = 'en-AU'
      const audio = sdk.AudioConfig.fromDefaultMicrophoneInput()
      const rec = new sdk.SpeechRecognizer(cfg, audio)
      const phrases = sdk.PhraseListGrammar.fromRecognizer(rec)
      for (const p of ['BP', 'sats', 'SpO2', 'GCS', 'confirm category', 'send the message', 'add to the waiting room', 'obs from the monitor', 'Alan Pierce', 'Grace Bennett', 'Margaret Reid', 'Robert Hale']) phrases.addPhrase(p)
      rec.recognizing = (_s, e) => { this.partial = e.result.text; this.emit() }
      rec.recognized = (_s, e) => {
        if (e.result.reason === sdk.ResultReason.RecognizedSpeech && e.result.text) this.finals.push(e.result.text)
        this.partial = ''
        this.emit()
      }
      rec.canceled = (_s, e) => {
        this.onStatus(e.errorDetails ? `Speech service: ${e.errorDetails}` : 'Dictation stopped.')
        this.stop()
      }
      rec.sessionStopped = () => this.stop()
      this.recognizer = rec as unknown as Recognizer
      this.onListening(true)
      this.onStatus('Azure AI Speech, en-AU. Audio goes to the speech service: demo data only.')
      rec.startContinuousRecognitionAsync(undefined, (err: string) => { this.onStatus(`Microphone: ${err}`); this.stop() })
    } catch (e) {
      this.onStatus(`Dictation could not start: ${e instanceof Error ? e.message : String(e)}. Type instead.`)
      this.stop()
    }
  }

  private emit() {
    const spoken = [...this.finals, this.partial].filter(Boolean).join(' ')
    this.onText([this.base, spoken].filter(Boolean).join(' '))
  }

  stop(): void {
    const r = this.recognizer
    this.recognizer = null
    this.onListening(false)
    if (r) {
      try { r.stopContinuousRecognitionAsync(() => r.close(), () => r.close()) } catch { /* already closed */ }
    }
  }

  toggle(continuing: string): void {
    if (this.recognizer) this.stop()
    else void this.start(continuing)
  }
}
