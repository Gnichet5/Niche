---
name: Liquid Minimalist UI Skill with Ambient Background
commands: ["@apply-premium-ui", "@polish"]
---

# Diretrizes Técnicas de Design (Estilo Fluido e Líquido)

## 1. Sistema de Cores (Suave e Orgânico)
- **Tema Claro:** `--bg-main: #f4f6f6;`, `--bg-panel: rgba(255, 255, 255, 0.25);`, `--text-main: #1c2022;`, `--accent: #bda682;`, `--blob-1: rgba(0, 0, 0, 0.07);`, `--blob-2: rgba(189, 166, 130, 0.15);`
- **Tema Escuro:** `--bg-main: #0e1111;`, `--bg-panel: rgba(20, 22, 22, 0.25);`, `--text-main: #e2e8f0;`, `--accent: #d4af37;`, `--blob-1: rgba(255, 255, 255, 0.05);`, `--blob-2: rgba(212, 175, 55, 0.08);`

## 2. Cenário e Fundo Orgânico (Blobs e Partículas)
O HTML deve conter uma estrutura de fundo (`<div class="ambient-background">`) que fica isolada atrás de toda a interface (`z-index: -1`).
- **Esferas Borradas (Blobs):** Devem usar `position: fixed;`, `border-radius: 50%;`, `filter: blur(80px);` e uma animação de flutuação ultra-lenta (`@keyframes float`).
- **Partículas Minimalistas:** Pequenos pontos nítidos (`width: 4px; height: 4px;`) espalhados estrategicamente com opacidade baixa (`0.3`), simulando pequenas gotas suspensas ou poeira de luz estática.

## 3. Glassmorphism Orgânico (Mais Transparente)
- `backdrop-filter: blur(32px) saturate(130%);`
- `background: var(--bg-panel);`
- `border: 1px solid rgba(255, 255, 255, 0.18);`
- `box-shadow: inset 0 1px 2px rgba(255, 255, 255, 0.2), 0 20px 50px rgba(0, 0, 0, 0.02);`
- `border-radius: 28px;`

## 4. Hover Estilo "Toque na Água" (Ondulação Suave)
- **Transição Padrão:** `transition: all 0.7s cubic-bezier(0.16, 1, 0.3, 1);`
- **Efeito Hover:** Expandir levemente (`transform: scale(1.015);`), suavizar a borda e ganhar um brilho interno (`box-shadow: inset 0 1px 6px rgba(255, 255, 255, 0.4), 0 20px 40px rgba(0, 0, 0, 0.03);`).
- **Efeito ao Clicar:** `transform: scale(0.985); transition: all 0.1s;`
