<<<<<<< HEAD
# Frontend — React dashboard (Phase 8)

```bash
# terminal 1 — API
export PYTHONPATH="$PWD/src:$PWD"
uvicorn backend.app.main:app --reload

# terminal 2 — dashboard
cd frontend
npm install      # first time only
npm run dev
```

Then open **http://127.0.0.1:5173**.

It opens on **13 November 2025, 03:00** — a real flood with 29 stations alerting
and 25 already under water. The last available timestamp (31 December) is dry
season, and opening on a quiet moment makes a working dashboard look broken.

## What is on screen

| | |
|---|---|
| **Map** | district polygons shaded by the share of that district's sensors alerting |
| **Now** | counts, the selected station's depth/rain chart, sensor table |
| **Trends** | city-wide rain and flooded-sensor counts, plus the worst hotspots 2019–2025 |
| **Alerts** | CAP messages that would be issued, marked `Test` |
| **Limits** | the model card — what this system can and cannot do |

Time controls step in 15-minute and 1-hour increments, or type a timestamp.

## Four design decisions that are about honesty, not taste

**The replay banner cannot be dismissed.** Everything shown is historical. A
dashboard that looks live is the easiest way for this project to mislead
somebody.

**Districts are polygons, never station pins.** Every station coordinate we hold
is a district centroid — all sensors in a district share one point. Pins would
place several markers where none of the sensors actually is.

**Districts with no sensors are drawn hollow, not green.** "No data" and "no
flooding" must not look the same.

**No predicted depth appears anywhere.** The depth model failed its coverage
check (43–63% against a 90% target). The station chart draws measured depth and
measured rain only — no forecast trajectory, because the model outputs a
probability, not a depth curve.

## The legend earns its space

A coloured map is the most over-readable thing in this system. The legend states
that shading is the share of a district's *few* sensors and **not a flood
extent** — when a district genuinely floods, typically only about a third of its
sensors register it.
=======
# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...

      // Remove tseslint.configs.recommended and replace with this
      tseslint.configs.recommendedTypeChecked,
      // Alternatively, use this for stricter rules
      tseslint.configs.strictTypeChecked,
      // Optionally, add this for stylistic rules
      tseslint.configs.stylisticTypeChecked,

      // Other configs...
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])

```

You can also install [eslint-plugin-react-x](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x'
import reactDom from 'eslint-plugin-react-dom'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...
      // Enable lint rules for React
      reactX.configs['recommended-typescript'],
      // Enable lint rules for React DOM
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])

```
>>>>>>> 977641cc39ef29cfe39959f8fa6625c9dc98eb3d
