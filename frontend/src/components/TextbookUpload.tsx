import { useState, useRef } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { api } from "@/lib/api"
import { notify } from "@/lib/toast"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TextbookAnalysis {
  detected_grade: string
  detected_subject: string
  detected_topic: string
  detected_chapter: string
  key_concepts: string[]
  content_summary: string
  language: string
  raw_text: string
}

interface TextbookUploadProps {
  onWorksheetGenerated: (worksheet: any) => void
  onRevisionGenerated: (revision: any) => void
  onFlashcardsGenerated: (flashcards: any) => void
}

type Step = "upload" | "analysis" | "generating"

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function TextbookUpload({
  onWorksheetGenerated,
  onRevisionGenerated,
  onFlashcardsGenerated,
}: TextbookUploadProps) {
  const [step, setStep] = useState<Step>("upload")
  const [images, setImages] = useState<File[]>([])
  const [previews, setPreviews] = useState<string[]>([])
  const [analyzing, setAnalyzing] = useState(false)
  const [analysis, setAnalysis] = useState<TextbookAnalysis | null>(null)
  const [generating, setGenerating] = useState(false)
  const [generatingType, setGeneratingType] = useState<string | null>(null)

  const fileInputRef = useRef<HTMLInputElement>(null)
  const cameraInputRef = useRef<HTMLInputElement>(null)

  // ── Image handling ──────────────────────────────────────────────────

  const addImages = (files: FileList | null) => {
    if (!files) return
    const newFiles = Array.from(files).slice(0, 3 - images.length)
    if (newFiles.length === 0) return

    const updatedImages = [...images, ...newFiles].slice(0, 3)
    setImages(updatedImages)

    // Generate previews
    const newPreviews = [...previews]
    newFiles.forEach(file => {
      const url = URL.createObjectURL(file)
      newPreviews.push(url)
    })
    setPreviews(newPreviews.slice(0, 3))
  }

  const removeImage = (idx: number) => {
    const updated = [...images]
    updated.splice(idx, 1)
    setImages(updated)

    URL.revokeObjectURL(previews[idx])
    const updatedPreviews = [...previews]
    updatedPreviews.splice(idx, 1)
    setPreviews(updatedPreviews)
  }

  // ── Step 1: Analyze ─────────────────────────────────────────────────

  const handleAnalyze = async () => {
    if (images.length === 0) return
    setAnalyzing(true)

    try {
      const formData = new FormData()
      images.forEach(img => formData.append("images", img))

      const response = await api.post("/api/v1/textbook/analyze", formData, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 30000,
      })

      setAnalysis(response.data)
      setStep("analysis")
      notify.success("Textbook page analyzed!")
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to analyze textbook page"
      notify.error(msg)
    } finally {
      setAnalyzing(false)
    }
  }

  // ── Step 2: Generate ────────────────────────────────────────────────

  const handleGenerate = async (outputType: "worksheet" | "revision" | "flashcards") => {
    if (!analysis) return
    setGenerating(true)
    setGeneratingType(outputType)
    setStep("generating")

    try {
      const response = await api.post("/api/v1/textbook/generate", {
        analysis,
        output_type: outputType,
        language: analysis.language,
      }, { timeout: 60000 })

      if (outputType === "worksheet") {
        onWorksheetGenerated(response.data)
      } else if (outputType === "revision") {
        onRevisionGenerated(response.data)
      } else {
        onFlashcardsGenerated(response.data)
      }

      notify.success(
        outputType === "worksheet" ? "Worksheet ready!" :
        outputType === "revision" ? "Revision notes ready!" :
        "Flashcards ready!"
      )
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : `Failed to generate ${outputType}`
      notify.error(msg)
      setStep("analysis") // Go back to let user retry
    } finally {
      setGenerating(false)
      setGeneratingType(null)
    }
  }

  const handleReset = () => {
    // Clean up preview URLs
    previews.forEach(url => URL.revokeObjectURL(url))
    setImages([])
    setPreviews([])
    setAnalysis(null)
    setStep("upload")
  }

  // ── Render: Upload step ─────────────────────────────────────────────

  if (step === "upload" || (step !== "analysis" && step !== "generating")) {
    return (
      <div className="space-y-6">
        <div className="text-center">
          <h3 className="text-lg font-bold text-[#1B4332] mb-1">Learn from Your Textbook</h3>
          <p className="text-sm text-muted-foreground">
            Photograph any page from your child's textbook. We'll read it and create practice material.
          </p>
        </div>

        {/* Drop zone */}
        <Card className="border-2 border-dashed border-[#1B4332]/20 bg-[#E8F5E9]/30 hover:bg-[#E8F5E9]/50 transition-colors">
          <CardContent className="py-10 text-center">
            <svg className="w-12 h-12 mx-auto text-[#1B4332]/40 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6.827 6.175A2.31 2.31 0 015.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 00-1.134-.175 2.31 2.31 0 01-1.64-1.055l-.822-1.316a2.192 2.192 0 00-1.736-1.039 48.774 48.774 0 00-5.232 0 2.192 2.192 0 00-1.736 1.039l-.821 1.316z" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 12.75a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0zM18.75 10.5h.008v.008h-.008V10.5z" />
            </svg>
            <p className="text-sm font-medium text-[#1B4332]/70 mb-4">
              Take a photo or upload from your gallery
            </p>
            <div className="flex justify-center gap-3">
              <Button
                variant="outline"
                size="sm"
                onClick={() => cameraInputRef.current?.click()}
                disabled={images.length >= 3}
                className="border-[#1B4332]/30 text-[#1B4332]"
              >
                <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6.827 6.175A2.31 2.31 0 015.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 00-1.134-.175 2.31 2.31 0 01-1.64-1.055l-.822-1.316a2.192 2.192 0 00-1.736-1.039 48.774 48.774 0 00-5.232 0 2.192 2.192 0 00-1.736 1.039l-.821 1.316z" />
                  <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 12.75a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0z" />
                </svg>
                Take Photo
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => fileInputRef.current?.click()}
                disabled={images.length >= 3}
                className="border-[#1B4332]/30 text-[#1B4332]"
              >
                <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
                </svg>
                Upload File
              </Button>
            </div>

            {/* Hidden inputs */}
            <input
              ref={cameraInputRef}
              type="file"
              accept="image/*"
              capture="environment"
              className="hidden"
              onChange={e => addImages(e.target.files)}
            />
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              multiple
              className="hidden"
              onChange={e => addImages(e.target.files)}
            />
          </CardContent>
        </Card>

        {/* Image previews */}
        {images.length > 0 && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <p className="text-sm font-medium text-foreground">{images.length}/3 page{images.length !== 1 ? "s" : ""} uploaded</p>
              {images.length < 3 && (
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="text-xs text-[#1B4332] hover:underline"
                >
                  + Add more
                </button>
              )}
            </div>
            <div className="flex gap-3">
              {previews.map((url, idx) => (
                <div key={idx} className="relative w-20 h-20 rounded-lg overflow-hidden border border-border/40 shadow-sm">
                  <img src={url} alt={`Page ${idx + 1}`} className="w-full h-full object-cover" />
                  <button
                    onClick={() => removeImage(idx)}
                    className="absolute top-0.5 right-0.5 w-5 h-5 bg-red-500 text-white rounded-full flex items-center justify-center text-xs hover:bg-red-600"
                    aria-label={`Remove image ${idx + 1}`}
                  >
                    &times;
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tips */}
        <div className="bg-[#FFF8E1] rounded-xl p-4 text-xs text-[#92400E] space-y-1">
          <p className="font-semibold text-sm mb-1">Tips for best results:</p>
          <p>&bull; Hold camera steady, avoid shadows</p>
          <p>&bull; Include the full page in the frame</p>
          <p>&bull; Upload up to 3 pages from the same chapter</p>
        </div>

        {/* Analyze button */}
        <Button
          className="w-full py-4 text-lg font-bold shadow-lg shadow-primary/20 transition-all hover:scale-[1.01] active:scale-[0.99] rounded-xl"
          onClick={handleAnalyze}
          disabled={images.length === 0 || analyzing}
          size="lg"
        >
          {analyzing ? (
            <span className="flex items-center gap-3">
              <span className="spinner !w-5 !h-5 !border-primary-foreground/30 !border-t-primary-foreground" />
              Reading your textbook...
            </span>
          ) : (
            <span className="flex items-center gap-3">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
              </svg>
              Analyze Page
            </span>
          )}
        </Button>
      </div>
    )
  }

  // ── Render: Analysis results ────────────────────────────────────────

  if (step === "analysis" && analysis) {
    return (
      <div className="space-y-6">
        <div className="text-center">
          <h3 className="text-lg font-bold text-[#1B4332] mb-1">We read your textbook page!</h3>
          <p className="text-sm text-muted-foreground">Choose what you'd like to create from this content.</p>
        </div>

        {/* Analysis card */}
        <Card className="border-[#1B4332]/20 bg-[#E8F5E9]/30">
          <CardContent className="p-5 space-y-3">
            <div className="flex items-start gap-3">
              <span className="text-2xl">📖</span>
              <div>
                <p className="font-bold text-[#1B4332]">{analysis.detected_chapter}</p>
                <p className="text-sm text-muted-foreground">
                  {analysis.detected_grade} &middot; {analysis.detected_subject} &middot; {analysis.language}
                </p>
              </div>
            </div>

            <div>
              <p className="text-xs font-semibold text-muted-foreground mb-1.5">Key concepts:</p>
              <div className="flex flex-wrap gap-1.5">
                {analysis.key_concepts.map((concept, idx) => (
                  <span
                    key={idx}
                    className="text-xs px-2 py-0.5 bg-white/80 border border-[#1B4332]/10 rounded-full text-[#1B4332]"
                  >
                    {concept}
                  </span>
                ))}
              </div>
            </div>

            <p className="text-sm text-muted-foreground italic">
              "{analysis.content_summary}"
            </p>
          </CardContent>
        </Card>

        {/* Output type cards */}
        <div>
          <p className="text-sm font-semibold text-foreground mb-3">What would you like to create?</p>
          <div className="grid grid-cols-3 gap-3">
            <button
              onClick={() => handleGenerate("worksheet")}
              disabled={generating}
              className="p-4 rounded-xl border-2 border-[#1B4332]/20 bg-white hover:bg-[#E8F5E9]/50 hover:border-[#1B4332]/40 transition-all text-center group"
            >
              <span className="text-2xl block mb-2">📝</span>
              <p className="text-sm font-bold text-[#1B4332]">Worksheet</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">10 questions from this chapter</p>
            </button>
            <button
              onClick={() => handleGenerate("revision")}
              disabled={generating}
              className="p-4 rounded-xl border-2 border-[#1B4332]/20 bg-white hover:bg-[#E8F5E9]/50 hover:border-[#1B4332]/40 transition-all text-center group"
            >
              <span className="text-2xl block mb-2">📖</span>
              <p className="text-sm font-bold text-[#1B4332]">Revision Notes</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">Summarize this chapter</p>
            </button>
            <button
              onClick={() => handleGenerate("flashcards")}
              disabled={generating}
              className="p-4 rounded-xl border-2 border-[#1B4332]/20 bg-white hover:bg-[#E8F5E9]/50 hover:border-[#1B4332]/40 transition-all text-center group"
            >
              <span className="text-2xl block mb-2">🃏</span>
              <p className="text-sm font-bold text-[#1B4332]">Flashcards</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">12 cards from this content</p>
            </button>
          </div>
        </div>

        {/* Back button */}
        <button
          onClick={handleReset}
          className="text-sm text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
          </svg>
          Upload different page
        </button>
      </div>
    )
  }

  // ── Render: Generating step ─────────────────────────────────────────

  return (
    <div className="space-y-6">
      <div className="text-center py-12">
        <div className="flex justify-center mb-6">
          <span className="spinner !w-8 !h-8 !border-[#1B4332]/30 !border-t-[#1B4332]" />
        </div>
        <p className="text-sm font-medium text-foreground">
          {generatingType === "worksheet" && "Generating worksheet from your textbook..."}
          {generatingType === "revision" && "Creating revision notes from your textbook..."}
          {generatingType === "flashcards" && "Building flashcards from your textbook..."}
          {!generatingType && "Generating..."}
        </p>
        <p className="text-xs text-muted-foreground mt-2">
          Based on: {analysis?.detected_chapter}
        </p>
      </div>
    </div>
  )
}
