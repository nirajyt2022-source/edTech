import { Card, CardContent } from '@/components/ui/card'

export interface WorksheetTemplate {
  id: string
  name: string
  description: string
  questionCount: number
  difficulty: string
  customInstructions: string
  icon: 'weekly' | 'test' | 'revision' | 'custom'
  tags: string[]
}

// eslint-disable-next-line react-refresh/only-export-components
export const TEMPLATES: WorksheetTemplate[] = [
  {
    id: 'weekly-practice',
    name: 'Weekly Practice',
    description: 'Quick daily-style practice with a focused topic. Great for homework.',
    questionCount: 8,
    difficulty: 'Easy',
    customInstructions: 'Create a light practice worksheet suitable for weekly homework. Mix 2-3 question types. Keep questions straightforward and confidence-building. Include 1-2 slightly challenging questions at the end.',
    icon: 'weekly',
    tags: ['5-10 Qs', 'Easy-Medium', 'Homework'],
  },
  {
    id: 'chapter-test',
    name: 'Chapter Test',
    description: 'Comprehensive assessment covering a full chapter. Includes all question types.',
    questionCount: 15,
    difficulty: 'Medium',
    customInstructions: 'Create a formal chapter test suitable for classroom assessment. Include a good mix of question types: multiple choice, fill in the blanks, true/false, and short answer. Progress from easy to hard. Include 2-3 application-based questions.',
    icon: 'test',
    tags: ['15-20 Qs', 'Medium-Hard', 'Assessment'],
  },
  {
    id: 'revision-sheet',
    name: 'Revision Sheet',
    description: 'Mixed-topic review pulling from multiple chapters. Ideal for exam prep.',
    questionCount: 12,
    difficulty: 'Medium',
    customInstructions: 'Create a revision worksheet that covers multiple subtopics within the selected topic area. Mix question types and difficulty levels. Include some questions that connect concepts across subtopics. Good for exam preparation and review.',
    icon: 'revision',
    tags: ['10-15 Qs', 'Mixed', 'Exam Prep'],
  },
]

const iconMap = {
  weekly: (
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" />
    </svg>
  ),
  test: (
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25zM6.75 12h.008v.008H6.75V12zm0 3h.008v.008H6.75V15zm0 3h.008v.008H6.75V18z" />
    </svg>
  ),
  revision: (
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182" />
    </svg>
  ),
  custom: (
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  ),
}

interface TemplateSelectorProps {
  selectedTemplate: string | null
  onSelect: (template: WorksheetTemplate | null) => void
}

export default function TemplateSelector({ selectedTemplate, onSelect }: TemplateSelectorProps) {
  return (
    <div>
      <label className="text-sm font-medium text-foreground mb-2 block">Worksheet Type</label>
      <div role="radiogroup" aria-label="Worksheet type" className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {TEMPLATES.map((template) => (
          <Card
            key={template.id}
            tabIndex={0}
            role="radio"
            aria-checked={selectedTemplate === template.id}
            className={`cursor-pointer transition-all border ${
              selectedTemplate === template.id
                ? 'border-primary/60 bg-primary/[0.03]'
                : 'border-border/30 hover:border-primary/20 hover:bg-secondary/30'
            }`}
            onClick={() => onSelect(template)}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(template); } }}
          >
            <CardContent className="py-4 px-3 text-center">
              <div className={`w-10 h-10 mx-auto mb-2 rounded-lg flex items-center justify-center ${
                selectedTemplate === template.id
                  ? 'bg-primary/15 text-primary'
                  : 'bg-secondary/50 text-muted-foreground'
              }`}>
                {iconMap[template.icon]}
              </div>
              <p className="font-medium text-sm text-foreground">{template.name}</p>
              <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{template.description}</p>
              <div className="flex flex-wrap justify-center gap-1 mt-2">
                {template.tags.map((tag) => (
                  <span key={tag} className="text-[10px] px-1.5 py-0.5 rounded-full bg-secondary text-muted-foreground">
                    {tag}
                  </span>
                ))}
              </div>
            </CardContent>
          </Card>
        ))}

        {/* Custom option */}
        <Card
          tabIndex={0}
          role="radio"
          aria-checked={selectedTemplate === 'custom'}
          className={`cursor-pointer transition-all border ${
            selectedTemplate === 'custom'
              ? 'border-primary/60 bg-primary/[0.03]'
              : 'border-border/30 hover:border-primary/20 hover:bg-secondary/30'
          }`}
          onClick={() => onSelect(null)}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(null); } }}
        >
          <CardContent className="py-4 px-3 text-center">
            <div className={`w-10 h-10 mx-auto mb-2 rounded-lg flex items-center justify-center ${
              selectedTemplate === 'custom'
                ? 'bg-primary/15 text-primary'
                : 'bg-secondary/50 text-muted-foreground'
            }`}>
              {iconMap.custom}
            </div>
            <p className="font-medium text-sm text-foreground">Custom</p>
            <p className="text-xs text-muted-foreground mt-1 line-clamp-2">Configure everything yourself</p>
            <div className="flex flex-wrap justify-center gap-1 mt-2">
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-secondary text-muted-foreground">
                Flexible
              </span>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
