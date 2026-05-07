/**
 * uriv-syncboard / frontend / src / components / CanvasROI.tsx
 *
 * FIX: canvas was 0×0 on mount because ResizeObserver fires asynchronously.
 *      We now force an initial size sync via a layout-effect + set dimensions
 *      directly on the element before the first draw call.
 *
 * Visual layers (bottom → top)
 *   1. Live JPEG frame
 *   2. Confirmed ROI — green dashed rectangle
 *   3. Drag preview — red dashed rectangle while drawing
 *   4. White flash overlay on BOARD_CLEARED
 *   5. Toast badge on BOARD_CLEARED
 */

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'

interface Props {
  frameDataUrl:  string | null
  boardCleared:  boolean
  onRoiSet:      (x: number, y: number, w: number, h: number) => void
  onRoiClear:    () => void
}

interface Rect { x: number; y: number; w: number; h: number }

const MIN_DRAG = 20   // px — minimum drag to register as an ROI

export default function CanvasROI({ frameDataUrl, boardCleared, onRoiSet, onRoiClear }: Props) {
  const canvasRef   = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const imgRef      = useRef<HTMLImageElement>(new window.Image())

  const [confirmedRoi, setConfirmedRoi] = useState<Rect | null>(null)
  const [dragRect,     setDragRect]     = useState<Rect | null>(null)
  const dragStart = useRef<{ x: number; y: number } | null>(null)
  const [flash, setFlash] = useState(false)

  // ── FIX: sync canvas pixel dimensions before first paint ─────────────────
  useLayoutEffect(() => {
    const canvas    = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container) return

    const sync = () => {
      const { width, height } = container.getBoundingClientRect()
      if (width > 0 && height > 0) {
        canvas.width  = width
        canvas.height = height
      }
    }
    sync()                          // immediate sync on mount

    const ro = new ResizeObserver(sync)
    ro.observe(container)
    return () => ro.disconnect()
  }, [])

  // ── Load new frame ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!frameDataUrl) return
    imgRef.current.src = frameDataUrl
  }, [frameDataUrl])

  // ── Board-clear flash ─────────────────────────────────────────────────────
  useEffect(() => {
    if (!boardCleared) return
    setFlash(true)
    const t = setTimeout(() => setFlash(false), 350)
    return () => clearTimeout(t)
  }, [boardCleared])

  // ── Animation loop ────────────────────────────────────────────────────────
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    let raf: number

    const draw = () => {
      raf = requestAnimationFrame(draw)
      const img = imgRef.current
      const { width: cw, height: ch } = canvas

      if (cw === 0 || ch === 0) return

      ctx.clearRect(0, 0, cw, ch)

      // 1. Frame
      if (img.complete && img.naturalWidth > 0) {
        ctx.drawImage(img, 0, 0, cw, ch)
      } else {
        // Placeholder while no frame yet
        ctx.fillStyle = '#0a0a1a'
        ctx.fillRect(0, 0, cw, ch)
        ctx.fillStyle = '#333'
        ctx.font = '14px monospace'
        ctx.textAlign = 'center'
        ctx.fillText('Waiting for stream…', cw / 2, ch / 2)
        ctx.textAlign = 'left'
      }

      // 2. Confirmed ROI
      if (confirmedRoi) {
        ctx.save()
        ctx.strokeStyle = '#4ade80'
        ctx.lineWidth   = 2
        ctx.setLineDash([6, 4])
        ctx.strokeRect(confirmedRoi.x, confirmedRoi.y, confirmedRoi.w, confirmedRoi.h)
        ctx.fillStyle = 'rgba(74,222,128,0.07)'
        ctx.fillRect(confirmedRoi.x, confirmedRoi.y, confirmedRoi.w, confirmedRoi.h)
        ctx.setLineDash([])
        ctx.fillStyle = '#4ade80'
        ctx.font      = 'bold 11px monospace'
        ctx.fillText('ROI', confirmedRoi.x + 4, Math.max(confirmedRoi.y - 5, 12))
        ctx.restore()
      }

      // 3. Drag preview
      if (dragRect) {
        ctx.save()
        ctx.strokeStyle = '#e94560'
        ctx.lineWidth   = 1.5
        ctx.setLineDash([5, 4])
        ctx.strokeRect(dragRect.x, dragRect.y, dragRect.w, dragRect.h)
        ctx.restore()
      }

      // 4. Flash overlay
      if (flash) {
        ctx.save()
        ctx.fillStyle = 'rgba(255,255,255,0.3)'
        ctx.fillRect(0, 0, cw, ch)
        ctx.restore()
      }
    }

    draw()
    return () => cancelAnimationFrame(raf)
  }, [confirmedRoi, dragRect, flash])

  // ── Coordinate mapping: canvas px → original frame px ────────────────────
  const toFrameCoords = useCallback(
    (cx: number, cy: number) => {
      const canvas = canvasRef.current!
      const img    = imgRef.current
      if (!img.naturalWidth) return { x: cx, y: cy }
      return {
        x: Math.round(cx * img.naturalWidth  / canvas.width),
        y: Math.round(cy * img.naturalHeight / canvas.height),
      }
    },
    [],
  )

  // ── Mouse handlers ────────────────────────────────────────────────────────
  const getPos = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const r = canvasRef.current!.getBoundingClientRect()
    return { x: e.clientX - r.left, y: e.clientY - r.top }
  }

  const onMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    dragStart.current = getPos(e)
    setDragRect(null)
  }

  const onMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!dragStart.current) return
    const { x, y } = getPos(e)
    const { x: sx, y: sy } = dragStart.current
    setDragRect({
      x: Math.min(sx, x), y: Math.min(sy, y),
      w: Math.abs(x - sx), h: Math.abs(y - sy),
    })
  }

  const onMouseUp = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!dragStart.current) return
    const { x: ex, y: ey } = getPos(e)
    const { x: sx, y: sy } = dragStart.current
    dragStart.current = null
    setDragRect(null)

    const w = Math.abs(ex - sx), h = Math.abs(ey - sy)
    if (w < MIN_DRAG || h < MIN_DRAG) return

    const roi: Rect = { x: Math.min(sx, ex), y: Math.min(sy, ey), w, h }
    setConfirmedRoi(roi)

    // Convert to frame-space coordinates
    const tl = toFrameCoords(roi.x, roi.y)
    const br = toFrameCoords(roi.x + roi.w, roi.y + roi.h)
    onRoiSet(tl.x, tl.y, br.x - tl.x, br.y - tl.y)
  }

  const clearRoi = () => {
    setConfirmedRoi(null)
    setDragRect(null)
    dragStart.current = null
    onRoiClear()
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div ref={containerRef} className="relative w-full h-full flex flex-col min-h-0">

      <canvas
        ref={canvasRef}
        className="flex-1 w-full cursor-crosshair bg-black min-h-0"
        style={{ display: 'block' }}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={() => { dragStart.current = null; setDragRect(null) }}
      />

      {/* Toolbar */}
      <div className="flex items-center gap-2 px-1 py-1 shrink-0">
        <span className="text-xs text-gray-500 select-none">
          {confirmedRoi
            ? `ROI: ${confirmedRoi.w}×${confirmedRoi.h} px on canvas`
            : 'Click and drag to select board region'}
        </span>
        {confirmedRoi && (
          <button
            onClick={clearRoi}
            className="ml-auto text-xs bg-gray-700 hover:bg-gray-600 text-gray-200
                       px-3 py-1 rounded transition-colors"
          >
            ✂ Clear ROI
          </button>
        )}
      </div>

      {/* Board-cleared toast */}
      {boardCleared && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2
                        bg-amber-500 text-black text-xs font-bold
                        px-4 py-1.5 rounded-full shadow-lg animate-bounce pointer-events-none">
          🧹 Board cleared — auto-saving…
        </div>
      )}
    </div>
  )
}
