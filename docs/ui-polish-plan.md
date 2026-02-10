# PracticeCraft AI — Enterprise UI Polish Plan

## Context
The app is functionally complete (Phase 3), but the UI tone is overly corporate — words like "pedagogical", "Terminate Session", "Execute Syllabus Mapping" undermine the calm, academic trust the PRDs call for. Border radii, font weights, and button sizes are also inconsistent across pages. This plan fixes tone + visual consistency without touching any functionality.

## Scope
- **YES**: Language/copy, border-radius, font-weight, button sizing, minor visual polish
- **NO**: New features, layout restructuring, component refactoring, business logic

---

## Phase 1: Language & Tone (Highest Impact)

Warm, simple, educator-friendly language. Replace corporate jargon with plain speech.

### `App.tsx`
| Line | Old | New |
|------|-----|-----|
| ~103 | "Assembling Workspace" | "Loading..." |
| ~105 | "Syncing your pedagogical data..." | "Preparing your workspace..." |
| ~121 | label: 'Monitor' | label: 'Dashboard' |
| ~128 | label: 'Roster' | label: 'Classes' |
| ~135 | label: 'Draft' | label: 'Create' |
| ~151 | label: 'Draft' (parent) | label: 'Create' |
| ~159 | label: 'Curriculum' | label: 'Syllabus' |
| ~281 | "Terminate Session" | "Sign Out" |

### `TeacherDashboard.tsx`
| Old | New |
|-----|-----|
| "Overseeing X distinct classroom groups..." | "Managing X classes. Your teaching materials, organized and ready." |
| "Welcome to your pedagogical command center..." | "Welcome to your workspace. Start by adding your first class." |
| "Draft Worksheets" | "Create Worksheets" |
| "Leverage AI to craft high-quality academic worksheets..." | "Generate worksheets tailored to your class curriculum." |
| "Roster Management" | "Manage Classes" |
| "Configure your classroom groups, subjects..." | "Organize your classes for quick worksheet creation." |
| "Classroom Roster" | "Your Classes" |
| "Initialize Class" | "Add First Class" |
| "Archived Worksheets" | "Recent Worksheets" |
| "No content has been generated yet." | "No worksheets created yet." |

### `ClassManager.tsx`
| Old | New |
|-----|-----|
| "Classroom Roster" (title) | "Your Classes" |
| "Coordinate your teaching groups..." | "Add and manage your classes to streamline worksheet creation." |
| "Update Parameters" / "Register New Group" | "Edit Class" / "Add New Class" |
| "Modify the configuration for..." | "Update the details for {name}." |
| "Define a new classroom entity..." | "Set up a new class to start generating worksheets." |
| "Identification" | "Class Name" |
| "Grade Level" | "Grade" |
| "Core Subject" | "Subject" |
| "Educational Board" | "Board" |
| "Commiting Changes..." | "Saving..." |
| "Sync Configuration" | "Save Changes" |
| "Establish Classroom Group" | "Create Class" |
| "Abandon" | "Cancel" |
| "Active Roster" | "All Classes" |
| "Roster is empty" | "No classes yet" |
| "Initialize your pedagogical workspace..." | "Add your first class to get started." |
| "Register First Class" | "Create First Class" |

### `SyllabusUpload.tsx`
| Old | New |
|-----|-----|
| "Syllabus Library" | "Syllabus" |
| "Establish the foundation for your content..." | "Choose a CBSE syllabus or upload your school's custom curriculum." |
| "CBSE Standards" | "CBSE Syllabus" |
| "Standardized Curriculum" | "Browse Curriculum" |
| "Select a grade and subject to explore the mapping..." | "Select a grade and subject to view the syllabus." |
| "Academic Subject" | "Subject" |
| "Content Structure" | "Chapters & Topics" |
| "Initiate Worksheet with this Syllabus" | "Use This Syllabus" |
| "Upload Interface" | "Upload Document" |
| "Provide a document to let our AI map out..." | "Upload a PDF or image and we'll extract the syllabus structure." |
| "Contextual Grade (Optional)" | "Grade (optional)" |
| "Expected Subject (Optional)" | "Subject (optional)" |
| "Deep Parsing in Progress..." | "Processing..." |
| "Execute Syllabus Mapping" | "Parse Syllabus" |
| "Unlock Institutional Workflows" | "Upload Your Own Syllabus" |
| "Customize learning by uploading your unique school syllabus..." | "Upload your school's syllabus to generate worksheets matched to your curriculum. Available on Pro." |
| "Confirm & Use Mapping" | "Use This Syllabus" |

### `RoleSelector.tsx`
| Old | New |
|-----|-----|
| "Professional Setup" (step 2 header) | "Tell Us More" |
| "Disciplines" | "Subjects You Teach" |
| "Grade Levels" | "Grades You Teach" |
| "Institutional Affiliation" | "School Name" |

### `SavedWorksheets.tsx`
| Old | New |
|-----|-----|
| "Classroom Repository" (teacher title) | "Saved Worksheets" |
| "Access and manage all worksheets generated..." | "Browse, download, or regenerate your saved worksheets." |

### `ChildProfiles.tsx`
| Old | New |
|-----|-----|
| "Learning Context" | "Notes" |

---

## Phase 2: Font Weight Reduction

Replace aggressive `font-black` with `font-bold` and normalize tracking. The app should feel calm, not LOUD.

### `App.tsx`
- Logo: `font-black` → `font-bold`
- Nav tabs (desktop): `font-black uppercase tracking-widest` → `font-bold uppercase tracking-wide`
- Nav tabs (mobile): `font-black uppercase tracking-tighter` → `font-semibold uppercase tracking-tight`
- Role label: `font-black uppercase tracking-tighter` → `font-medium uppercase tracking-tight`

### `TeacherDashboard.tsx`
- Stat values: `font-black` → `font-bold`
- Stat labels: `font-bold uppercase tracking-widest` → `font-medium uppercase tracking-wide`
- Class metadata: `font-black uppercase tracking-widest` → `font-semibold uppercase tracking-wide`
- Worksheet metadata: `font-black uppercase tracking-tighter` → `font-medium uppercase tracking-tight`

### `ClassManager.tsx`
- Form labels: `font-bold text-foreground/70 uppercase tracking-widest` → `font-semibold text-foreground/80` (drop uppercase)
- Card metadata: `font-black uppercase tracking-widest` → `font-semibold uppercase tracking-wide`

### `SavedWorksheets.tsx`
- Date group headers: `tracking-[0.2em]` → `tracking-wide`

### `SyllabusUpload.tsx`
- Form labels: `font-bold text-foreground/80` → `font-semibold text-foreground/80`
- File metadata: `font-bold text-muted-foreground/50 uppercase tracking-widest` → `font-medium text-muted-foreground/50 uppercase tracking-wide`
- Upload CTA label: `font-bold text-muted-foreground/40 uppercase tracking-widest` → `font-medium text-muted-foreground/40 uppercase tracking-wide`

### `RoleSelector.tsx`
- Step labels: `font-black uppercase tracking-widest` → `font-semibold uppercase tracking-wide`

---

## Phase 3: Border Radius Standardization

Standardize to 3 tiers:
- `rounded-lg` (8px) — inputs, small buttons, badges, tags
- `rounded-xl` (12px) — cards, sections, dropdowns, standard buttons
- `rounded-2xl` (16px) — modals, hero containers, special emphasis only

### Key changes:
- RoleSelector dialog: `rounded-3xl` → `rounded-2xl`
- RoleSelector role cards: `rounded-3xl` → `rounded-2xl`
- ClassManager class cards: `rounded-3xl` → `rounded-2xl`
- ClassManager form container: `rounded-3xl` → `rounded-2xl`
- Mobile bottom nav container: `rounded-3xl` → `rounded-2xl`
- SyllabusUpload drag zone: `rounded-3xl` → `rounded-2xl`
- WorksheetGenerator generate button: `rounded-2xl` → `rounded-xl`
- All CTA buttons currently `rounded-2xl` → `rounded-xl`
- Form select triggers: keep `rounded-xl`
- Form inputs: keep `rounded-xl` (already consistent)

---

## Phase 4: Button Height Normalization

Standardize primary CTA height to `py-4` (from excessive `py-7`).

### Files affected:
- `WorksheetGenerator.tsx`: Generate button `py-7` → `py-4`, remove `h-auto`
- `ClassManager.tsx`: Submit `py-7 h-auto` → `py-4 h-auto`, Cancel `py-7 h-auto` → `py-4 h-auto`
- `ChildProfiles.tsx`: Submit `py-6 h-auto` → `py-4 h-auto`
- `SyllabusUpload.tsx`: "Use This Syllabus" `py-7 h-auto` → `py-4 h-auto`, Upload button `py-7 h-auto` → `py-4 h-auto`, Upgrade button `py-6 h-auto` → `py-4 h-auto`
- `RoleSelector.tsx`: Back/Submit `py-6` → `py-4`

---

## Phase 5: Minor Visual Polish

- `WorksheetGenerator.tsx`: Question number badge `rounded` → `rounded-lg`
- `App.tsx`: Loading spinner text — remove `animate-pulse` (feels anxious)

---

## Files Modified (10 total)
1. `frontend/src/App.tsx`
2. `frontend/src/pages/TeacherDashboard.tsx`
3. `frontend/src/pages/ClassManager.tsx`
4. `frontend/src/pages/SyllabusUpload.tsx`
5. `frontend/src/pages/SavedWorksheets.tsx`
6. `frontend/src/pages/ChildProfiles.tsx`
7. `frontend/src/pages/WorksheetGenerator.tsx`
8. `frontend/src/pages/Auth.tsx` (minor — only if font weight cleanup needed)
9. `frontend/src/components/RoleSelector.tsx`
10. `frontend/src/components/TemplateSelector.tsx` (only if radius cleanup needed)

## Verification
1. `pnpm run lint` — 0 errors
2. `pnpm run build` — passes
3. Visual spot-check: Auth → Role Select → Dashboard → Create → Saved → Classes → Profiles → Syllabus
4. Both roles (teacher + parent) checked
5. No functionality or data flow changes
