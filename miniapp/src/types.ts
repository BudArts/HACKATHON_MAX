export type Role = 'student' | 'parent' | 'teacher' | 'administrator' | 'guest';

export type ConsentPurpose = 'service' | 'notifications' | 'ai_processing';

export type TaskStatus = 'active' | 'solved' | 'abandoned';
export type TaskSubject = 'math' | 'physics';

export interface UserView {
  id: string;
  role: Role;
  first_name: string | null;
  last_name: string | null;
  username: string | null;
  locale: string;
  grade?: number | null;
  is_active: boolean;
  has_phone: boolean;
  has_email: boolean;
  created_at: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface ConsentState {
  purpose: ConsentPurpose;
  granted: boolean;
  policy_code: string;
  policy_version: string;
  granted_at: string | null;
  revoked_at: string | null;
}

export interface AuthResponse {
  user: UserView;
  tokens: TokenPair | null;
  consents: ConsentState[];
  onboarding_required: boolean;
}

export interface TaskView {
  id: string;
  subject: TaskSubject;
  grade: number;
  topic: string | null;
  status: TaskStatus;
  steps: number;
  summary: string | null;
  started_at: string;
  solved_at: string | null;
  messages: number;
}

export interface ThreadMessage {
  author: 'student' | 'tutor';
  content: string;
  created_at: string;
}

export interface TaskDetail extends TaskView {
  thread: ThreadMessage[];
}

export interface TaskStatistics {
  total: number;
  solved: number;
  active: number;
  recent_topics: string[];
}

export interface TopicStat {
  topic: string;
  total: number;
  solved: number;
}

export interface GradeOverview {
  grade: number;
  students: number;
  tasks_total: number;
  tasks_solved: number;
  topics: TopicStat[];
}

export interface RiskStudent {
  user_id: string;
  name: string;
  grade: number;
  unsolved: number;
  stuck_topics: string[];
}

export interface ChildView {
  user_id: string;
  name: string;
  grade: number | null;
}

export interface DigestView {
  student: ChildView;
  started: number;
  solved: number;
  topics: string[];
  daily: { day: string; started: number; solved: number }[];
  last_activity_at: string | null;
}

export interface DevUser {
  max_user_id: number;
  role: Role;
  first_name: string | null;
  last_name: string | null;
}

export interface DevInitData {
  init_data: string;
  max_user_id: number;
}

export interface PolicyView {
  code: string;
  version: string;
  title: string;
  body: string;
}

export interface PersonalDataReport {
  profile: UserView;
  consents: ConsentState[];
  tasks_total: number;
  notifications_total: number;
  audit_entries: Record<string, unknown>[];
}
