import { api } from './api'

export interface CurriculumSubject {
  name: string
  region: string
  source?: string
  skills: string[]
  logic_tags: string[]
  depth: 'core' | 'reinforcement'
}

interface SubjectsResponse {
  grade: number
  region: string
  subjects: CurriculumSubject[]
}

interface SubjectDetailResponse {
  grade: number
  subject: string
  region: string
  source?: string
  skills: string[]
  logic_tags: string[]
  depth: string
  stage: string
}

export async function fetchSubjects(
  grade: number,
  region: string,
  includeReinforcement = false
): Promise<CurriculumSubject[]> {
  const params = new URLSearchParams({
    region,
    include_reinforcement: String(includeReinforcement),
  })
  const response = await api.get<SubjectsResponse>(
    `/api/curriculum/subjects/${grade}?${params}`
  )
  return response.data.subjects
}

export async function fetchSkills(
  grade: number,
  subject: string,
  region: string
): Promise<SubjectDetailResponse> {
  const encodedSubject = encodeURIComponent(subject)
  const response = await api.get<SubjectDetailResponse>(
    `/api/curriculum/${grade}/${encodedSubject}?region=${region}`
  )
  return response.data
}
