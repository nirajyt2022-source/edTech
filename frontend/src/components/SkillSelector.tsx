import { useState } from 'react'

interface Props {
  skills: string[]
  logicTags: string[]
  onSelectionChange: (skills: string[], logicTags: string[]) => void
  reinforcementSkills?: string[]
}

export default function SkillSelector({ skills, logicTags, onSelectionChange, reinforcementSkills }: Props) {
  const [selectedSkill, setSelectedSkill] = useState<string | null>(null)
  const [showReinforcement, setShowReinforcement] = useState(false)

  const selectSkill = (skill: string) => {
    // Clicking the active skill deselects it
    const next = selectedSkill === skill ? null : skill
    setSelectedSkill(next)
    onSelectionChange(next ? [next] : [], logicTags)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h4 className="text-sm font-bold text-foreground">Practice Skills</h4>
        {selectedSkill ? (
          <span className="text-[10px] font-bold text-primary bg-primary/5 px-2 py-0.5 rounded-md border border-primary/10">
            1 selected
          </span>
        ) : (
          <span className="text-[10px] font-bold text-muted-foreground bg-secondary/50 px-2 py-0.5 rounded-md border border-border/40">
            None selected
          </span>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        {skills.map((skill) => {
          const isSelected = selectedSkill === skill
          return (
            <button
              key={skill}
              type="button"
              onClick={() => selectSkill(skill)}
              className={`px-3.5 py-2 rounded-xl text-xs font-bold border transition-all duration-200 ${
                isSelected
                  ? 'bg-primary text-primary-foreground border-primary shadow-md shadow-primary/15 scale-[1.02]'
                  : 'bg-card/40 text-muted-foreground border-border/60 hover:border-primary/40 hover:bg-card'
              }`}
            >
              {skill}
            </button>
          )
        })}
      </div>

      {reinforcementSkills && reinforcementSkills.length > 0 && (
        <div className="pt-2">
          <button
            type="button"
            onClick={() => setShowReinforcement(!showReinforcement)}
            className="flex items-center gap-2 text-xs font-bold text-muted-foreground/70 hover:text-foreground transition-colors"
          >
            <svg
              className={`w-3.5 h-3.5 transition-transform duration-200 ${showReinforcement ? 'rotate-90' : ''}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2.5}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
            </svg>
            Additional Practice ({reinforcementSkills.length} skills)
          </button>

          {showReinforcement && (
            <div className="flex flex-wrap gap-2 mt-3 pl-5 animate-in fade-in slide-in-from-top-2 duration-300">
              {reinforcementSkills.map((skill) => {
                const isSelected = selectedSkill === skill
                return (
                  <button
                    key={skill}
                    type="button"
                    onClick={() => selectSkill(skill)}
                    className={`px-3 py-1.5 rounded-xl text-[11px] font-bold border transition-all duration-200 ${
                      isSelected
                        ? 'bg-accent/20 text-accent-foreground border-accent/30 shadow-sm'
                        : 'bg-secondary/20 text-muted-foreground/60 border-border/40 hover:border-accent/30 hover:bg-secondary/40'
                    }`}
                  >
                    {skill}
                  </button>
                )
              })}
            </div>
          )}
        </div>
      )}

      {logicTags.length > 0 && (
        <div className="flex items-center gap-2 pt-1">
          <span className="text-[10px] font-bold text-muted-foreground/50 uppercase tracking-widest">Focus:</span>
          {logicTags.map((tag) => (
            <span
              key={tag}
              className="text-[10px] font-bold text-primary/70 bg-primary/5 px-2 py-0.5 rounded-md border border-primary/10"
            >
              {tag}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
