/**
 * uriv-syncboard / frontend / src / hooks / useSocket.ts
 *
 * FIXES applied here
 * ──────────────────
 * 1. Removed `as any` cast — SessionInfo now includes db_session_id
 * 2. Ping typed as ClientMsg (no more TypeScript error)
 * 3. dbSessionId preserved across session_update messages that arrive
 *    before the DB flush completes (null-coalesce keeps old value)
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { socket } from '../api/socket'
import type { ClientMsg, OcrLine, PageSnapshot, SessionInfo, StatusMsg } from '../types'

export interface SyncBoardState {
  connected:    boolean
  frameDataUrl: string | null
  ocrText:      string
  confidence:   number
  ocrLines:     OcrLine[]
  boardCleared: boolean
  session:      SessionInfo
  status:       StatusMsg | null
  dbSessionId:  string | null
}

const DEFAULT_SESSION: SessionInfo = {
  name:          'New Session',
  page_count:    0,
  pages:         [],
  db_session_id: null,
}

export function useSocket() {
  const [state, setState] = useState<SyncBoardState>({
    connected:    false,
    frameDataUrl: null,
    ocrText:      '',
    confidence:   0,
    ocrLines:     [],
    boardCleared: false,
    session:      DEFAULT_SESSION,
    status:       null,
    dbSessionId:  null,
  })

  const [lastCapturedSeq, setLastCapturedSeq] = useState<number | null>(null)
  const clearTimer  = useRef<ReturnType<typeof setTimeout>>()
  const statusTimer = useRef<ReturnType<typeof setTimeout>>()
  const pingTimer   = useRef<ReturnType<typeof setInterval>>()

  useEffect(() => {
    socket.connect()

    // Keepalive — backend handles { type: 'ping' } and replies { type: 'pong' }
    pingTimer.current = setInterval(() => {
      if (socket.isConnected) socket.send({ type: 'ping' })
    }, 25_000)

    const remove = socket.onMessage((msg) => {
      switch (msg.type) {

        case 'frame':
          setState(s => ({
            ...s,
            connected:    true,
            frameDataUrl: `data:image/jpeg;base64,${msg.data}`,
          }))
          break

        case 'ocr_update':
          setState(s => ({
            ...s,
            ocrText:    msg.text,
            confidence: msg.confidence,
            ocrLines:   msg.lines,
          }))
          break

        case 'board_cleared':
          setState(s => ({ ...s, boardCleared: true }))
          clearTimeout(clearTimer.current)
          clearTimer.current = setTimeout(
            () => setState(s => ({ ...s, boardCleared: false })),
            2000,
          )
          break

        case 'page_captured':
          setLastCapturedSeq(msg.page.seq)
          break

        case 'session_update':
          setState(s => ({
            ...s,
            session:    msg.session,
            // FIX: no more `as any` — SessionInfo now has db_session_id
            // Preserve old value if new message arrives before DB flush
            dbSessionId: msg.session.db_session_id ?? s.dbSessionId,
          }))
          break

        case 'status':
          setState(s => ({ ...s, status: { message: msg.message, level: msg.level } }))
          clearTimeout(statusTimer.current)
          statusTimer.current = setTimeout(
            () => setState(s => ({ ...s, status: null })),
            5000,
          )
          break

        case 'error':
          setState(s => ({ ...s, status: { message: msg.message, level: 'error' } }))
          break

        case 'pong':
          // keepalive acknowledged — no-op
          break
      }
    })

    const hb = setInterval(
      () => setState(s => ({ ...s, connected: socket.isConnected })),
      1500,
    )

    return () => {
      remove()
      clearInterval(hb)
      clearInterval(pingTimer.current)
      clearTimeout(clearTimer.current)
      clearTimeout(statusTimer.current)
    }
  }, [])

  const send = useCallback((msg: ClientMsg) => socket.send(msg), [])

  return { state, send, lastCapturedSeq }
}
