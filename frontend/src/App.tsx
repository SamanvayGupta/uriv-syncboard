/**
 * uriv-syncboard / frontend / src / App.tsx
 *
 * FIXES:
 *  1. sessionDbId now comes from hook state (was always undefined before)
 *  2. WS URL uses relative path → works through Vite proxy (no hardcoded host)
 *  3. Better connection status messaging
 */

import { useRef } from 'react'
import { Video, Image as ImageIcon, Square, Camera, Upload, MonitorPlay } from 'lucide-react'

import CanvasROI from './components/CanvasROI'
import LiveNotes from './components/LiveNotes'
import { useSocket } from './hooks/useSocket'

// FIX: Use relative URL so Vite proxy handles routing (works both local + Docker)
const API_BASE = ''   // empty = relative to current host

export default function App() {
  const { state, send, lastCapturedSeq } = useSocket()
  const fileInputRef  = useRef<HTMLInputElement>(null)
  const videoInputRef = useRef<HTMLInputElement>(null)

  // ── Source handlers ────────────────────────────────────────────────────────

  const startWebcam = () => send({ type: 'start_webcam', device_index: 0 })
  const stopCapture = () => send({ type: 'stop' })

  const openVideo  = () => videoInputRef.current?.click()
  const openImages = () => fileInputRef.current?.click()

  const handleVideoFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const formData = new FormData()
    formData.append('files', file)
    try {
      const res  = await fetch(`${API_BASE}/api/upload`, { method: 'POST', body: formData })
      const data = await res.json()
      send({ type: 'start_video', path: data.paths[0] })
    } catch {
      alert('Upload failed — is the backend running?')
    }
    e.target.value = ''
  }

  const handleImageFiles = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    if (!files.length) return
    const formData = new FormData()
    files.forEach(f => formData.append('files', f))
    try {
      const res  = await fetch(`${API_BASE}/api/upload`, { method: 'POST', body: formData })
      const data = await res.json()
      send({ type: 'start_images', paths: data.paths })
    } catch {
      alert('Upload failed — is the backend running?')
    }
    e.target.value = ''
  }

  const handleRoiSet   = (x: number, y: number, w: number, h: number) =>
    send({ type: 'set_roi', x, y, w, h })
  const handleRoiClear = () => send({ type: 'clear_roi' })

  return (
    <div className="flex flex-col h-screen bg-[#1a1a2e] text-white overflow-hidden">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="flex items-center gap-3 px-5 py-2.5 bg-[#16213e] border-b border-white/5 shrink-0">
        <MonitorPlay size={20} className="text-[#e94560]" />
        <h1 className="text-base font-bold tracking-tight">SyncBoard</h1>
        <span className="text-xs text-gray-500 hidden sm:block">Smart Whiteboard Assistant</span>

        {/* Connection dot */}
        <div className="ml-auto flex items-center gap-1.5">
          <span className={`w-2 h-2 rounded-full ${state.connected ? 'bg-green-400' : 'bg-red-500 animate-pulse'}`} />
          <span className="text-[11px] text-gray-500">
            {state.connected ? 'Connected' : 'Connecting…'}
          </span>
        </div>
      </header>

      {/* ── Body ───────────────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">

        {/* Left — video + toolbar */}
        <main className="flex flex-col flex-1 overflow-hidden p-3 gap-2 min-w-0">

          {/* Source toolbar */}
          <div className="flex flex-wrap items-center gap-2 shrink-0">
            <span className="text-[10px] font-bold tracking-widest text-gray-500 mr-1">
              SOURCE
            </span>
            <ToolBtn onClick={startWebcam} colour="red"  icon={<Camera size={13}/>}>Webcam</ToolBtn>
            <ToolBtn onClick={openVideo}   colour="teal" icon={<Video  size={13}/>}>Video</ToolBtn>
            <ToolBtn onClick={openImages}  colour="teal" icon={<ImageIcon size={13}/>}>Images</ToolBtn>
            <ToolBtn onClick={stopCapture} colour="dark" icon={<Square size={13}/>}>Stop</ToolBtn>

            <input ref={videoInputRef} type="file" accept="video/*"  className="hidden" onChange={handleVideoFile}  />
            <input ref={fileInputRef}  type="file" accept="image/*" multiple className="hidden" onChange={handleImageFiles} />

            <span className="ml-auto flex items-center gap-1 text-xs text-gray-600">
              <Upload size={11} /> Upload via Video / Images buttons
            </span>
          </div>

          {/* Canvas */}
          <div className="flex-1 rounded-xl overflow-hidden border border-white/5 bg-black min-h-0">
            <CanvasROI
              frameDataUrl={state.frameDataUrl}
              boardCleared={state.boardCleared}
              onRoiSet={handleRoiSet}
              onRoiClear={handleRoiClear}
            />
          </div>

          <p className="text-[11px] text-gray-600 text-center shrink-0">
            Drag on the feed to set ROI · Click <strong className="text-gray-400">Capture Page</strong> or enable Auto-detect
          </p>
        </main>

        {/* Right — notes panel */}
        <aside className="w-[340px] shrink-0 bg-[#16213e] border-l border-white/5 overflow-y-auto">
          <LiveNotes
            connected       ={state.connected}
            ocrText         ={state.ocrText}
            confidence      ={state.confidence}
            session         ={state.session}
            status          ={state.status}
            lastCapturedSeq ={lastCapturedSeq}
            dbSessionId     ={state.dbSessionId}
            apiBase         ={API_BASE}
            onCapture       ={() => send({ type: 'capture_page' })}
            onSetReference  ={() => send({ type: 'set_reference' })}
            onToggleAuto    ={(en) => send({ type: 'toggle_auto', enabled: en })}
            onDeletePage    ={(seq) => send({ type: 'delete_page', page_id: seq })}
            onNewSession    ={() => send({ type: 'new_session' })}
          />
        </aside>
      </div>
    </div>
  )
}

// ── Sub-component ─────────────────────────────────────────────────────────────
function ToolBtn({ children, onClick, colour, icon }: {
  children: React.ReactNode; onClick: () => void
  colour: 'red' | 'teal' | 'dark'; icon: React.ReactNode
}) {
  const bg = { red: 'bg-[#e94560] hover:bg-[#c73050]', teal: 'bg-[#0f3460] hover:bg-[#1a4a80]', dark: 'bg-[#2a2a3a] hover:bg-[#3a3a4a]' }[colour]
  return (
    <button onClick={onClick}
      className={`flex items-center gap-1.5 text-xs font-semibold text-white px-3 py-1.5 rounded-md transition-colors ${bg}`}>
      {icon}{children}
    </button>
  )
}
