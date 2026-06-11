---
name: copy-patterns
description: Mushin's Korean copy voice and string conventions — register (해요체), person (나/내, never 당신), the understated 무심/無心 no-hype tone, banned gamer-loanword register, the 無心 framing/gloss requirement, the no-account/guest copy rules, and the centralized-strings i18n rule. Use whenever writing any user-facing Korean string — onboarding, button labels, empty states, nudges, notifications.
---

# Mushin copy patterns

Mushin is a Korean "육성 RPG of yourself." The brand is 무심/無心 ("no-mind") —
quiet, egoless, unburdened. The copy is a supportive companion, never a hype-man.

## Register & person

- **해요체 throughout** — polite-friendly. Not 합니다체 (too corporate), not 반말
  (presumptuous).
- **Address the user as their own first person — 나 / 내**, never 당신. This is a
  raising-sim *of yourself*: "내 검도", "오늘의 나". 당신 creates distance and reads
  like an ad.

## Tone

- Quietly on the user's side. **Celebrate by stating the fact plainly**
  ("3단계 달성") and letting the number speak. No exclamation spam.
- **No false urgency or guilt.** Banned: "지금 기록 안 하면 스트릭 끊겨요!",
  "기록이 사라질 수 있어요", any guilt-trip — it contradicts no-mind.
- XP/level language is fine as **quiet structure**, never as loud decoration.

## Banned register

- English gamer loanwords stacked for hype: 콤보!, 미션 클리어!, 레벨업!! 대박!!.
- Exclamation-mark spam and ⚠️-style alarm in normal flows.

## Brand framing (무심/無心)

- **무심 never ships bare.** Pair it with the hanja 無心 + a one-line gloss on the
  store listing, splash, and onboarding screen 1. Sample gloss:
  "힘 빼고, 무심하게. 매일 쌓이는 나." The gloss *reclaims* the everyday 무심하다
  ("indifferent") into the intended 無心 ("no-mind / egoless flow").

## No-account / guest copy

- The entry choice **leads with `그냥 시작하기`** (계정 없이 바로); sign-in is the
  calm secondary. Honest, not a dark pattern.
- Frame the no-account path as **"계정 없이, 나만 보는 기록"** (no account,
  only-you).
- **Never claim "아무 데도 안 보내요 / nothing leaves your device."** Under the
  anonymous-server design the data IS on our server — that line would be false.
- The guest **upgrade nudge** is gift-framed and fires at the first level-up:
  "여기까지 온 기록, 계정에 연결해 두면 계속 이어져요" `[연결하기] [나중에]`. It is
  dismissible, respects "나중에", and never blocks logging. No loss/urgency framing.

## i18n

- **Every user-facing string is centralized** in one strings module — never
  hardcode copy in a template (web or HXML). Korean only at launch; other locales
  are a later addition, not a rewrite.
- Keep layouts width-flexible: Korean is often shorter than its equivalents, so
  don't bake Korean character widths into the home-card numerals or "advance"
  lines.
