# MedSchedule AI — Frontend

Next.js 16 (App Router) + React 19 + TypeScript + Tailwind CSS v4 + shadcn/ui.

See the [root README](../README.md) for the full project overview, architecture and deployment.

```bash
cp .env.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000/api
npm install
npm run dev                  # http://localhost:3000
npm run lint && npm run build
```

Key folders: `src/components/landing` (animated landing), `src/components/tour` (first-run tour),
`src/components/workspace`, `grid`, `integration`, `copilot`, `analytics`, and `src/lib/api.ts` (backend client).
