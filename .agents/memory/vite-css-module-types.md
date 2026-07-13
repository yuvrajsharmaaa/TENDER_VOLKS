---
name: Vite CSS module types in TypeScript
description: TypeScript build fails for side-effect CSS imports in Vite unless a `vite-env.d.ts` declaration is present.
---

**Rule:** When a React + Vite + TypeScript project imports `*.css` as a side-effect (`import "./index.css"`), the TypeScript compiler will fail with `Cannot find module or type declarations for side-effect import of './index.css'` unless the project declares the module.

**Why:** Vite projects often omit the stock `vite-env.d.ts` file (which normally carries `/// <reference types="vite/client" />`). Without that reference, TypeScript has no ambient declaration for `*.css`, and `tsc -b` rejects the import even though Vite handles it fine at runtime.

**How to apply:**
- Create `frontend/src/vite-env.d.ts` (or restore the file if it was deleted) with:
  ```typescript
  /// <reference types="vite/client" />
  declare module "*.css" {
    const classes: { readonly [key: string]: string };
    export default classes;
  }
  ```
- Verify with `cd frontend && npm run build`.
- Keep the file even if it feels like boilerplate; it is the canonical Vite + TS solution.
