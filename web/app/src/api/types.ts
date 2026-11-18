// The API contract: the engine's routes (web/engine/pathfinder_engine/routes.py). Field names in camelCase.

export type Deployment = 'minimum' | 'standard' | 'full'
export type Outcome = 'B' | 'D' | 'R1' | 'R2' | 'R3'
export type ArrivalMode = 'By car' | 'Walked in' | 'By bus or train' | 'By taxi' | 'By ambulance' | 'With police'
export type TravelMode = 'walk' | 'bus' | 'car'
export type Cohort = 'mh' | 'p65' | 'other'
export type Stage = 'waiting' | 'inCare' | 'closed'
export type FollowTier = 1 | 2 | 3 | 4
export type FollowStatus = 'open' | 'noAnswer' | 'closed'
export type ServiceKind =
  | 'ed' | 'urgentCare' | 'gp' | 'pharmacy' | 'mentalHealth' | 'safeHaven' | 'virtualED' | 'phone' | 'homeCare'

export interface Vitals {
  pulse?: number; systolic?: number; diastolic?: number; spo2?: number
  resp?: number; temp?: number; gcs?: number; pain?: number
}

export interface ETA { p10: number; p50: number; p90: number; ahead: number; rangeText: string }

export interface FollowUp {
  tier: FollowTier; tierTitle: string; reasons: string[]
  risk7?: number; risk28?: number; riskN?: number; riskBasis: string
  status: FollowStatus; attempts: number; lastAttemptAt?: number
  result?: string; nextStep?: string; closedAt?: number
  aloOffered: boolean; messageSent: boolean; dueMinutes: number; policy: string
}

export interface Episode {
  id: number; name: string; age: number; sex: string; cohort: Cohort
  complaint: string; complaintKey: string; ats: number; arrival: number; arrivalMode: ArrivalMode
  holdFromCall?: boolean; holdReason?: string; stage: Stage
  calledAt?: number; careEnds?: number; outcome?: Outcome; outcomeAt?: number
  leaveReason?: string; redirectService?: string
  priorVisits: number; daysSinceLast?: number; priorDNW: boolean
  flags: string[]; vitals?: Vitals; etaConsent?: boolean; etaSentAt?: number
  isHero?: boolean; intakeSeconds?: number; descriptor?: string; transcript?: string
  homeLat: number; homeLon: number; homeSuburb: string; followUp?: FollowUp
}

export interface EpisodeView extends Episode {
  eta?: ETA; waitedMinutes: number; targetMinutes: number; mayLeaveSoon: boolean
  dueText?: string; outcomeLabel?: string; arrivalModeShort: string; travel: TravelMode; problem: string
}

export interface Banner { text: string; systemImage: string; tone: 'info' | 'warning' | 'success'; episodeId?: number }

export interface Persona {
  id: string; name: string; age: number; sex: string; script: string
  category: number; note: string; label: string; short: string
}

export interface DemoIntake extends IntakeResult {
  open: boolean; transcript: string; confirmed?: number | null; eta?: ETA | null; messageSent: boolean; showMessage: boolean
  heroId?: number | null; startedAtUtc?: string; message?: string
}
export interface DemoState {
  running: boolean; caption?: string | null; step: number; transcriptSoFar?: string | null; listening?: boolean
  finished?: boolean; narrated?: boolean; personaId?: string; tab?: string | null; followId?: number | null
  callingId?: number | string | null; rightDoorId?: number | null; intake?: DemoIntake | null
}

export interface Candidate { id: number; name: string; age: number; isHero: boolean; outcome?: string | null; stage?: Stage; homeSuburb?: string; arrivalModeShort?: string }

export interface PublishedTriple { waiting: number; inEd: number; t4AvgWaitMin: number }
export interface HospitalSource { takenText: string; takenAt: string; url: string }
export interface Hospital { id: string; name: string; short: string; published: PublishedTriple; source: HospitalSource }
export interface HospitalRow extends PublishedTriple { id: string; name: string; short: string; suburbs: string[] }
export interface HospitalsResponse { hospitals: HospitalRow[]; takenText: string; takenAt: string; url: string }

export interface State {
  now: number; clockText: string; speed: number; running: boolean; deployment: Deployment
  lastTickUtc: string; version: number
  ed: { name: string; simulated: true }
  hospital?: Hospital | null
  counters: { waiting: number; inCare: number; longestWait: number; mayLeave: number }
  waiting: EpisodeView[]
  followCases: EpisodeView[]
  openActionCount: number
  rightDoorCandidates: Candidate[]
  queueHistory: { minute: number; waiting: number }[]
  nextToBeCalled?: { id: number; samples: number[] }
  banner?: Banner
  persona: Persona; personaChoice: string; showCaptions: boolean; speakFeedback: boolean
  demo?: DemoState | null
  intakeMessageTemplate: string
  tabs?: string[]
  rightDoorId?: number | null
}

export interface RuleHit { ats: number; text: string; source: 'ACEM descriptor' | 'WA triage descriptor' | 'Demo threshold' }

export interface IntakeForm {
  name?: string; age?: number; sex?: string; arrivalMode?: string; complaintKey?: string; complaint?: string
  duration?: string; redFlags: string[]; mh: string[]; vitals: Vitals; redFlagLabels: string[]; mhLabels: string[]
}

export interface DemoRecord {
  name: string; age: number; sex: string; priorVisits: number; daysSinceLast?: number
  lastOutcome?: string; priorDNW: boolean; note: string
}

export type IntakeCommand = `confirm:${number}` | 'send' | 'finish' | 'fromMonitor' | 'redirect'

export interface IntakeResult {
  form: IntakeForm; hits: RuleHit[]; suggested?: number; record?: DemoRecord
  commands: IntakeCommand[]; monitorVitals?: Vitals
}

export interface IntakeSubmit {
  transcript: string; typed: string; confirmed?: number; messageSent: boolean; startedAt: string; monitorVitals?: Vitals
}

export interface NoteTemplate {
  id: string; title: string; cohort: Cohort; style: string; text: string
  expect: { complaintKey: string; suggested: number; cohort: Cohort }
}
export interface TemplatesResponse { templates: NoteTemplate[] }

export interface Hex { q: number; r: number }

export interface CareService {
  id: string; name: string; kind: ServiceKind; x?: number | null; y?: number | null
  contact: string; hoursText: string; goodFor: string; suits?: Cohort[]; symbol?: string
}

export interface RightDoorOption {
  service: CareService; minutes?: number | null; minutesText: string; opensIn: number; openText: string
  fit: number; score: number; route: Hex[]; pinned000?: boolean; rank: number
}

export interface RightDoorResult {
  episode: EpisodeView; purpose: 'redirectNow' | 'nextTime'; mode: TravelMode
  blockers: string[]; message: string; options: RightDoorOption[]; remote: RightDoorOption[]
  search: { rings: { k: number; hexes: Hex[]; found: string[] }[]; hexCount: number; needs: string[]; complete?: boolean }
  field: { hex: Hex; minutes: number }[]
  home: Hex; homeCoord: [number, number]; homeXY?: [number, number]
  edFirst?: boolean; busWait?: number
}

export interface KPIMetro {
  publishedT4AvgWaitMin: number
  simulatedT4WaitMin: { baseline: number; withRedirects: number }
  newArrivalT4WaitMin?: { baseline: number; withRedirects: number }
  redirectedShare: number
  waitingNow: { baseline: number; withRedirects: number }
  horizonMinutes: number; replicas: number; takenText: string; method: string
}

export interface KPI {
  metro?: KPIMetro | null
  captureSeconds: number[]
  etaShareWaiting: number
  todayDNWRate: number
  rContactShare: { done: number; total: number; notYetDue: number }
  namedNextStepShare: { done: number; total: number }
  returns?: number
  arrivalsByHour: { hour: number; actual: number; expected: number }[]
  baselines: {
    dnw_rate?: number; dnw_ats123_share?: number; median_wait_min?: number
    returns?: { cohort: string; outcome: string; ret7?: number; ret28?: number }[]
    [k: string]: unknown
  }
  weekly?: { week: string; [k: string]: number | string }[]
  queueHistory?: { minute: number; waiting: number }[]
}

export interface Unit {
  id: string; name: string; kind: 'connector' | 'store' | 'model' | 'function' | 'surface'
  tier: Deployment; plugsInto: string; gives: string; from: string[]
}

export interface Network {
  suburbs: { name: string; x: number; y: number; spread?: number }[]
  corridors: [number, number][][]
  roads?: [number, number][][]
  services: CareService[]
  hexSize: number
  ed?: { lat: number; lon: number }
  hospitalName?: string
  disclaimer?: string
}

export interface Settings {
  speed?: number; running?: boolean; deployment?: Deployment
  personaChoice?: string; showCaptions?: boolean; speakFeedback?: boolean
  hospitalId?: string
}
