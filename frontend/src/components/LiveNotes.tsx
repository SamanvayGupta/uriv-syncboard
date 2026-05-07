/**
 * uriv-syncboard / frontend / src / components / LiveNotes.tsx
 *
 * FIXES:
 *  1. Accepts apiBase prop so export URLs are relative (Vite proxy compatible)
 *  2. Shows clearer message when dbSessionId not set yet
 *  3. Export button shows spinner per-format correctly
 */

import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import {
  Camera, FileText, FileType, Presentation,
  FileJson, AlignLeft, Hash, Trash2, Plus,
  ChevronRight, Wifi, WifiOff, Zap,
} from 'lucide-react'
import type { PageSnapshot, SessionInfo, StatusMsg, ExportFmt } from '../types'

function confColour(c: number) {
  if (c > 70) return 'text-green-400'
  if (c > 40) return 'text-amber-400'
  return 'text-red-400'
}

const EXPORTS: { fmt: ExportFmt; label: string; icon: React.ReactNode }[] = [
  { fmt: 'pdf',      label: 'PDF',        icon: <FileText     size={13} /> },
  { fmt: 'docx',     label: 'Word',       icon: <FileType     size={13} /> },
  { fmt: 'pptx',     label: 'PowerPoint', icon: <Presentation size={13} /> },
  { fmt: 'markdown', label: 'Markdown',   icon: <Hash         size={13} /> },
  { fmt: 'txt',      label: 'Plain Text', icon: <AlignLeft    size={13} /> },
  { fmt: 'json',     label: 'JSON',       icon: <FileJson     size={13} /> },
]

interface Props {
  connected:       boolean
  ocrText:         string
  confidence:      number
  session:         SessionInfo
  status:          StatusMsg | null
  lastCapturedSeq: number | null
  dbSessionId:     string | null      // FIX: was sessionDbId: string | undefined
  apiBase:         string             // FIX: new — relative or absolute
  onCapture:       () => void
  onSetReference:  () => void
  onToggleAuto:    (enabled: boolean) => void
  onDeletePage:    (seq: number) => void
  onNewSession:    () => void
}

export default function LiveNotes({
  connected, ocrText, confidence, session, status,
  lastCapturedSeq, dbSessionId, apiBase,
  onCapture, onSetReference, onToggleAuto, onDeletePage, onNewSession,
}: Props) {
  const [autoOn,      setAutoOn]    = useState(false)
  const [selectedSeq, setSelectedSeq] = useState<number | null>(null)
  const [exporting,   setExporting] = useState<ExportFmt | null>(null)
  const [exportMsg,   setExportMsg] = useState('')

  const selectedPage = session.pages.find(p => p.seq === selectedSeq) ?? null

  const toggleAuto = () => {
    const next = !autoOn
    setAutoOn(next)
    onToggleAuto(next)
  }

  const handleExport = async (fmt: ExportFmt) => {
    if (!dbSessionId) {
      setExportMsg('Capture at least one page first — then export.')
      setTimeout(() => setExportMsg(''), 3000)
      return
    }
    setExporting(fmt)
    setExportMsg('')
    try {
      const ext = fmt === 'markdown' ? 'md' : fmt
      const url = `${apiBase}/api/sessions/${dbSessionId}/export/${fmt}`
      const res = await fetch(url)
      if (!res.ok) {
        const txt = await res.text()
        throw new Error(txt || res.statusText)
      }
      const blob   = await res.blob()
      const objUrl = URL.createObjectURL(blob)
      const a      = document.createElement('a')
      a.href     = objUrl
      a.download = `${session.name}.${ext}`
      a.click()
      URL.revokeObjectURL(objUrl)
      setExportMsg(`✓ Downloaded ${session.name}.${ext}`)
      setTimeout(() => setExportMsg(''), 4000)
    } catch (err) {
      setExportMsg(`Export failed: ${String(err)}`)
    } finally {
      setExporting(null)
    }
  }

  return (
    <aside className="flex flex-col h-full w-full overflow-hidden">

      {/* Connection badge */}
      <div className={`flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold shrink-0
                       ${connected ? 'bg-green-900/40 text-green-400' : 'bg-red-900/40 text-red-400'}`}>
        {connected ? <Wifi size={11} /> : <WifiOff size={11} />}
        {connected ? 'Connected to backend' : 'Disconnected — is the backend running?'}
      </div>

      {/* Status bar */}
      {status && (
        <div className={`px-4 py-1.5 text-xs border-b border-white/5 shrink-0
                         ${status.level === 'success' ? 'text-green-400' :
                           status.level === 'error'   ? 'text-red-400'   : 'text-gray-400'}`}>
          {status.level === 'error' && '⚠ '}{status.message}
        </div>
      )}

      {/* Live OCR */}
      <Section title="LIVE OCR">
        <div className="flex items-center justify-between mb-1.5 px-4">
          <span className="text-xs text-gray-500">Extracted text</span>
          <span className={`text-xs font-mono ${confColour(confidence)}`}>
            {confidence > 0 ? `${confidence.toFixed(1)}% conf` : '—'}
          </span>
        </div>

        <div className="mx-3 rounded-md bg-[#0d1b2a] px-3 py-2.5
                        min-h-[72px] max-h-[160px] overflow-y-auto
                        text-sm text-gray-200 font-mono leading-relaxed
                        prose prose-invert prose-sm prose-p:my-0.5">
          {ocrText.trim()
            ? <ReactMarkdown>{ocrText}</ReactMarkdown>
            : <span className="text-gray-600 text-xs">
                {connected ? 'Start a source to see OCR…' : 'Waiting for backend…'}
              </span>
          }
        </div>

        <div className="flex flex-wrap gap-2 px-3 mt-2.5">
          <ActionBtn onClick={onCapture}      colour="red"  icon={<Camera size={12}/>}>Capture Page</ActionBtn>
          <ActionBtn onClick={onSetReference} colour="teal" icon={<Zap    size={12}/>}>Set Reference</ActionBtn>
          <button
            onClick={toggleAuto}
            className={`ml-auto text-xs px-2.5 py-1 rounded transition-colors
                        ${autoOn ? 'bg-amber-600 text-white' : 'bg-[#1a2a3a] text-gray-400 hover:text-white'}`}>
            {autoOn ? '⏸ Auto ON' : '▶ Auto OFF'}
          </button>
        </div>
      </Section>

      <Divider />

      {/* Session pages */}
      <Section title="SESSION PAGES" className="flex-1 overflow-hidden flex flex-col min-h-0">
        <div className="flex items-center justify-between px-4 mb-1">
          <span className="text-xs text-gray-500">
            {session.name} · {session.page_count} page{session.page_count !== 1 ? 's' : ''}
          </span>
          <button onClick={onNewSession}
            className="flex items-center gap-1 text-xs text-teal-400 hover:text-teal-300 transition-colors">
            <Plus size={11} /> New
          </button>
        </div>

        <ul className="flex-1 overflow-y-auto mx-3 rounded-md bg-[#0d1b2a] divide-y divide-white/5 min-h-0">
          {session.pages.length === 0 && (
            <li className="px-3 py-5 text-xs text-gray-600 text-center">
              No pages captured yet.<br />
              <span className="text-gray-700">Click "Capture Page" or enable Auto-detect.</span>
            </li>
          )}
          {session.pages.map(page => (
            <li key={page.seq}
              onClick={() => setSelectedSeq(page.seq === selectedSeq ? null : page.seq)}
              className={`flex items-center gap-2 px-3 py-2 cursor-pointer transition-colors group
                          ${page.seq === lastCapturedSeq ? 'bg-green-900/30' : ''}
                          ${page.seq === selectedSeq ? 'bg-[#1a3050] text-white' : 'hover:bg-white/5 text-gray-300'}`}>
              <FileText size={13} className="shrink-0 text-gray-500" />
              <span className="flex-1 text-xs">
                <span className="font-semibold">Page {page.seq}</span>
                <span className="ml-2 text-gray-500 text-[11px]">
                  {new Date(page.timestamp).toLocaleTimeString()}
                </span>
              </span>
              <span className={`text-[10px] ${confColour(page.confidence)}`}>{page.confidence.toFixed(0)}%</span>
              <ChevronRight size={11} className="text-gray-600" />
              <button onClick={(e) => { e.stopPropagation(); onDeletePage(page.seq) }}
                className="opacity-0 group-hover:opacity-100 text-red-500 hover:text-red-400 transition-all ml-1"
                title="Delete page">
                <Trash2 size={12} />
              </button>
            </li>
          ))}
        </ul>

        {selectedPage && (
          <div className="mx-3 mt-2 rounded-md bg-[#0d1b2a] px-3 py-2
                          max-h-[90px] overflow-y-auto text-xs text-gray-300 font-mono leading-relaxed shrink-0">
            {selectedPage.text.trim() || <span className="text-gray-600">(no text detected)</span>}
          </div>
        )}
      </Section>

      <Divider />

      {/* Export */}
      <Section title="EXPORT" className="shrink-0">
        {!dbSessionId && session.page_count === 0 && (
          <p className="px-4 pb-1 text-[11px] text-gray-600">
            Capture a page first — exports are saved to the database automatically.
          </p>
        )}

        <div className="grid grid-cols-3 gap-1.5 px-3 pb-3">
          {EXPORTS.map(({ fmt, label, icon }) => (
            <button key={fmt} onClick={() => handleExport(fmt)}
              disabled={exporting !== null}
              className="flex flex-col items-center gap-1 py-2 px-1
                         bg-[#0f3460] hover:bg-[#1a4a80] rounded-md
                         text-gray-200 text-[11px] font-medium transition-colors
                         disabled:opacity-50 disabled:cursor-wait">
              {exporting === fmt
                ? <span className="text-sm animate-spin">⏳</span>
                : icon}
              {label}
            </button>
          ))}
        </div>

        {exportMsg && (
          <p className={`px-4 pb-2 text-[11px] ${exportMsg.startsWith('✓') ? 'text-green-400' : 'text-amber-400'}`}>
            {exportMsg}
          </p>
        )}
      </Section>

    </aside>
  )
}

// ── Sub-components ─────────────────────────────────────────────────────────

function Section({ title, children, className = '' }: {
  title: string; children: React.ReactNode; className?: string
}) {
  return (
    <div className={`py-2 ${className}`}>
      <p className="text-[10px] font-bold tracking-widest text-red-500 px-4 mb-2">{title}</p>
      {children}
    </div>
  )
}

function Divider() {
  return <div className="h-px bg-white/5" />
}

function ActionBtn({ children, onClick, colour, icon }: {
  children: React.ReactNode; onClick: () => void
  colour: 'red' | 'teal'; icon: React.ReactNode
}) {
  const bg = colour === 'red'
    ? 'bg-[#e94560] hover:bg-[#c73050]'
    : 'bg-[#0f8b8d] hover:bg-[#0a7070]'
  return (
    <button onClick={onClick}
      className={`flex items-center gap-1.5 text-xs font-semibold text-white px-3 py-1.5 rounded transition-colors ${bg}`}>
      {icon}{children}
    </button>
  )
}
