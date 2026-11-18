# Kairo web

The voice-first React UI for the Kairo lab. Built with Vite, React 19, TypeScript (strict) and Zustand; tested with Vitest and Testing Library.

```
npm install
npm run dev      # http://localhost:5173, proxies /api and /ws to the Python server on :8000
npm run build    # writes the production bundle into ../src/kairo/server/static
npm run check    # typecheck + lint + tests
```

Run the Python server separately (`kairo serve`). In production the server serves the built bundle.

## Structure

```
src/
  api/          wire protocol (types.ts), reconnecting socket, REST client, session singleton
  state/        Zustand stores. callStore.ts holds a pure reducer: server message -> state patch
  lib/          pure helpers (formatting, orb geometry, audio playback, scenario labels)
  components/   design-system primitives (Orb, Dock, Sheet, Pill, IconButton, Waveform...)
  features/
    call/         Home, Conversation, Listening overlay, voice capture
    board/        Memory board (lamps), ledger, mobile Lab screen
    experiments/  run form, saved runs, results table and charts
    research/     findings page, reading numbers from saved runs
    settings/     call settings sheet
  app/          shell (two-column desktop layout), routes, menu
  styles/       design tokens and global styles
  test/         setup and shared fixtures
```

Conventions: feature code imports from `@/api`, `@/state`, `@/components` and `@/lib`, never from another feature's internals. Anything with logic (reducers, formatters, geometry, run selection) is a pure function with its own test. Colours, radii and shadows come only from `styles/tokens.css`.

## Protocol

`api/types.ts` mirrors `src/kairo/server/session.py`. Change both together; `state/callStore.test.ts` and the Python `tests/test_server.py` pin each side.
