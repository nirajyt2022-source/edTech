// Worksheet types
export interface Question {
  id: string
  type: 'multiple_choice' | 'fill_blank' | 'short_answer' | 'true_false' | 'matching'
  text: string
  options?: string[]
  correctAnswer?: string | string[]
  explanation?: string
  difficulty: 'easy' | 'medium' | 'hard'
}

export interface Worksheet {
  id: string
  title: string
  subject: string
  gradeLevel: string
  topic: string
  questions: Question[]
  createdAt: string
  updatedAt: string
}

export interface WorksheetGenerationRequest {
  subject: string
  gradeLevel: string
  topic: string
  numQuestions: number
  questionTypes: Question['type'][]
  difficulty: Question['difficulty']
  customInstructions?: string
}

// Syllabus types
export interface SyllabusUnit {
  name: string
  topics: string[]
  estimatedWeeks?: number
}

export interface Syllabus {
  id: string
  name: string
  subject: string
  gradeLevel: string
  units: SyllabusUnit[]
  createdAt: string
}

// User types
export interface User {
  id: string
  email: string
  name?: string
  role: 'teacher' | 'admin'
  createdAt: string
}
