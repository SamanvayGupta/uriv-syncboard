/**
 * uriv-syncboard / frontend / src / api / socket.ts
 *
 * FIX (macOS): Use a relative WebSocket URL so it goes through the
 * Vite dev-server proxy → backend.  Direct ws://localhost:8000 bypasses
 * the proxy and causes CORS failures when running locally.
 *
 * The Vite proxy rewrites  ws://localhost:5173/ws  →  ws://localhost:8000/ws
 */

import type { ClientMsg, ServerMsg } from '../types'

function getWsUrl(): string {
  // In production build, use the env var if set
  const explicit = import.meta.env.VITE_WS_URL
  if (explicit) return explicit

  // In Vite dev server: use relative path so proxy handles it
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host     = window.location.host   // e.g. "localhost:5173"
  return `${protocol}//${host}/ws`
}

type Handler = (msg: ServerMsg) => void

export class SyncBoardSocket {
  private ws:       WebSocket | null = null
  private handlers: Set<Handler>     = new Set()
  private _reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private _reconnectDelay = 1000   // ms, doubles on each retry up to 10 s
  private _closed = false

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN) return
    this._closed = false
    const url = getWsUrl()
    console.info('[SyncBoard WS] connecting to', url)
    this.ws = new WebSocket(url)

    this.ws.onopen = () => {
      console.info('[SyncBoard WS] connected')
      this._reconnectDelay = 1000   // reset backoff
    }

    this.ws.onclose = (ev) => {
      if (!this._closed) {
        console.warn('[SyncBoard WS] closed (code=%d) — retry in %dms', ev.code, this._reconnectDelay)
        this._reconnectTimer = setTimeout(() => this.connect(), this._reconnectDelay)
        this._reconnectDelay = Math.min(this._reconnectDelay * 2, 10_000)
      }
    }

    this.ws.onerror = (e) => console.error('[SyncBoard WS] error', e)

    this.ws.onmessage = (e) => {
      try {
        const msg: ServerMsg = JSON.parse(e.data)
        this.handlers.forEach(h => h(msg))
      } catch {
        // ignore malformed frames
      }
    }
  }

  disconnect() {
    this._closed = true
    if (this._reconnectTimer) clearTimeout(this._reconnectTimer)
    this.ws?.close()
    this.ws = null
  }

  send(msg: ClientMsg) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg))
    } else {
      console.warn('[SyncBoard WS] not connected — queuing retry', msg.type)
      // Retry once after 1 s
      setTimeout(() => {
        if (this.ws?.readyState === WebSocket.OPEN) {
          this.ws.send(JSON.stringify(msg))
        }
      }, 1000)
    }
  }

  onMessage(handler: Handler) {
    this.handlers.add(handler)
    return () => this.handlers.delete(handler)
  }

  get isConnected() {
    return this.ws?.readyState === WebSocket.OPEN
  }
}

// Singleton — one connection shared across the whole app
export const socket = new SyncBoardSocket()
