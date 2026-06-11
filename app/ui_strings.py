"""Centralized Korean UI copy for the web renderer.

Every user-facing string in ``app/templates/web/**`` and
``app/templates/components/**`` comes from this module — no Korean string
literals in templates (grep-checked by
``tests/integration/test_web.py::test_no_hardcoded_korean_in_templates``).

Voice (see ``.claude/skills/copy-patterns``): 해요체, 나/내-person (never 당신),
understated — no hype, no urgency/guilt framing. The 무심/無心 brand never ships
without its hanja + a one-line gloss.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Brand
# ---------------------------------------------------------------------------

APP_NAME = "무심"
APP_NAME_HANJA = "無心"
APP_GLOSS = "힘 빼고, 매일 쌓이는 나."

# ---------------------------------------------------------------------------
# Entry screen (first run)
# ---------------------------------------------------------------------------

ENTRY_TITLE = "무심"
ENTRY_TAGLINE = "내가 꾸준히 해온 것들의 기록"

ENTRY_START_GUEST = "그냥 시작하기"
ENTRY_START_GUEST_SUB = "계정 없이, 나만 보는 기록"
ENTRY_START_GUEST_NOTE = "기록은 서버에 안전하게 보관돼요. 나중에 계정에 연결할 수 있어요."

ENTRY_DIVIDER = "또는"

ENTRY_SIGNIN_KAKAO = "카카오로 계속하기"
ENTRY_SIGNIN_GOOGLE = "구글로 계속하기"
ENTRY_SIGNIN_EMAIL = "이메일로 계속하기"

ENTRY_CONSENT_NOTICE = "계속 진행하면 개인정보 처리방침에 동의하는 것으로 간주돼요."
ENTRY_CONSENT_LINK_TEXT = "개인정보처리방침"
ENTRY_CONSENT_SUFFIX = "을 읽고 동의해요. (필수)"

# ---------------------------------------------------------------------------
# Home (character sheet)
# ---------------------------------------------------------------------------

HOME_TITLE = "내 기록"
HOME_EMPTY = "아직 시작한 활동이 없어요."

# Hero numeral suffixes / labels
HOME_LEVEL_PREFIX = ""  # the level label itself (e.g. "초단") is the hero text
HOME_COUNT_UNIT = "회"  # generic running-count unit ("3회")
HOME_RUNNING_LABEL = "누적"
HOME_PROGRESSION_LABEL = "현재 단계"

HOME_LOG_BUTTON = "기록하기"
HOME_STREAK_LABEL = "연속"
HOME_STREAK_DAYS_UNIT = "일째"

HOME_NEXT_LEVEL_PREFIX = "다음"
HOME_NO_NEXT_LEVEL = "최고 단계예요"

# ---------------------------------------------------------------------------
# Quick-add / log sheet
# ---------------------------------------------------------------------------

LOG_SHEET_TITLE = "기록하기"
LOG_SUBMIT = "기록 남기기"
LOG_CANCEL = "닫기"

LOG_OCCURRED_AT_LABEL = "날짜와 시간"
LOG_MEMO_LABEL = "메모"
LOG_MEMO_PLACEHOLDER = "오늘은 어땠나요"
LOG_COUNT_LABEL_SUFFIX = ""  # field_def.label is used directly
LOG_SCALE_LABEL_SUFFIX = ""

LOG_TAG_ADD_NEW = "+ 태그 추가"
LOG_TAG_ADD_PLACEHOLDER = "새 태그 이름"
LOG_TAG_ADD_CONFIRM = "추가"
LOG_TAG_ADD_CANCEL = "취소"

LOG_SUCCESS_NOTICE = "기록했어요."

# ---------------------------------------------------------------------------
# Match-list sub-form (tournament entries)
# ---------------------------------------------------------------------------

MATCH_LIST_OPPONENT_LABEL = "상대"
MATCH_LIST_SCORE_LABEL = "점수"
MATCH_LIST_RESULT_LABEL = "결과"

MATCH_RESULT_WIN = "승"
MATCH_RESULT_LOSS = "패"
MATCH_RESULT_DRAW = "무"

MATCH_LIST_ADD_ROW = "+ 경기 추가"
MATCH_LIST_REMOVE_ROW = "삭제"

# ---------------------------------------------------------------------------
# Sub-tally detail screen
# ---------------------------------------------------------------------------

DETAIL_BACK = "홈으로"

# ---------------------------------------------------------------------------
# Competition stats (tournament sub-tallies with a match_list field)
# ---------------------------------------------------------------------------

STATS_TITLE = "전적"

STATS_RECORD_WINS = "승"
STATS_RECORD_LOSSES = "패"
STATS_RECORD_DRAWS = "무"

STATS_WIN_RATE_LABEL = "승률"
STATS_WIN_RATE_NONE = "기록 없음"
STATS_WIN_RATE_BASIS_PREFIX = "결정된"
STATS_WIN_RATE_BASIS_UNIT = "경기 기준"

STATS_TIMELINE_TITLE = "최근 경기"
STATS_TIMELINE_EMPTY = "아직 기록된 경기가 없어요."

STATS_HEAD_TO_HEAD_TITLE = "상대 전적"
STATS_HEAD_TO_HEAD_EMPTY = "아직 상대 기록이 없어요."

# ---------------------------------------------------------------------------
# Stats: counts, streak, calendar, heatmap
# ---------------------------------------------------------------------------

STATS_SUMMARY_TITLE = "기록 요약"

STATS_PERIOD_WEEK = "이번 주"
STATS_PERIOD_MONTH = "이번 달"
STATS_PERIOD_YEAR = "올해"
STATS_PERIOD_LIFETIME = "전체"
STATS_AVG_PER_WEEK = "주 평균"

STREAK_CURRENT_LABEL = "현재 연속"
STREAK_LONGEST_LABEL = "최장 연속"
STREAK_DAYS_UNIT = "일"

CALENDAR_TITLE = "달력"
CALENDAR_PREV_MONTH = "이전 달"
CALENDAR_NEXT_MONTH = "다음 달"
CALENDAR_WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
CALENDAR_DAY_ENTRIES_TITLE = "이날의 기록"
CALENDAR_DAY_ENTRIES_EMPTY = "이날은 기록이 없어요."
CALENDAR_DAY_CLOSE = "닫기"

HEATMAP_TITLE = "지난 1년"
HEATMAP_ARIA_LABEL = "지난 365일 활동 기록"

# ---------------------------------------------------------------------------
# Tag-frequency / scale-distribution sections
# ---------------------------------------------------------------------------

TAG_FREQUENCY_EMPTY = "아직 태그 기록이 없어요."
TAG_FREQUENCY_THIS_PERIOD_PREFIX = "이번 달"

SCALE_DISTRIBUTION_EMPTY = "아직 기록이 없어요."
SCALE_DISTRIBUTION_AVERAGE_LABEL = "평균"

# ---------------------------------------------------------------------------
# Progression status
# ---------------------------------------------------------------------------

PROGRESSION_TITLE = "단계"

PROGRESSION_CURRENT_LABEL = "현재 단계"
PROGRESSION_NO_CURRENT = "아직 시작 전이에요"

PROGRESSION_NEXT_LABEL = "다음 단계"
PROGRESSION_NO_NEXT = "최고 단계예요"

PROGRESSION_ELIGIBLE = "다음 단계로 넘어갈 수 있어요"
PROGRESSION_NOT_ELIGIBLE = "아직 조건을 채우는 중이에요"

PROGRESSION_TIME_REMAINING_PREFIX = "앞으로"
PROGRESSION_TIME_REMAINING_DAYS_UNIT = "일"
PROGRESSION_TIME_HELD_PREFIX = "보유 기간"
PROGRESSION_TIME_HELD_YEARS_UNIT = "년"

PROGRESSION_COUNT_REMAINING_PREFIX = "앞으로"
PROGRESSION_COUNT_REMAINING_UNIT = "회 더"
PROGRESSION_COUNT_PROGRESS_UNIT = "회"

PROGRESSION_AGE_REQUIREMENT_PREFIX = "만"
PROGRESSION_AGE_REQUIREMENT_SUFFIX = "세 이상"
PROGRESSION_AGE_UNKNOWN_NOTE = "나이 정보가 없어 충족 여부를 표시할 수 없어요."

PROGRESSION_PREREQ_PREFIX = "먼저 필요"
PROGRESSION_PREREQ_HELD = "보유"
PROGRESSION_PREREQ_NOT_HELD = "미보유"

PROGRESSION_EVENT_PASS_PREFIX = "합격 기록"
PROGRESSION_EVENT_NEED_PASS = "심사 합격이 필요해요"

PROGRESSION_MANUAL_NOTE = "직접 기록하면 반영돼요"

PROGRESSION_TRACK_DAN = "단"
PROGRESSION_TRACK_SHOGO = "칭호"
PROGRESSION_TRACK_TIER = "단계"

# ---------------------------------------------------------------------------
# Guest upgrade nudge (fires at first progression level-up)
# ---------------------------------------------------------------------------

UPGRADE_NUDGE_TITLE = "여기까지 온 기록, 계정에 연결해 두면 계속 이어져요"
UPGRADE_NUDGE_CONNECT = "연결하기"
UPGRADE_NUDGE_LATER = "나중에"

LEVEL_UP_NOTICE = "단계가 올랐어요"

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

FOOTER_PRIVACY = "개인정보처리방침"

# ---------------------------------------------------------------------------
# Privacy policy page
# ---------------------------------------------------------------------------

PRIVACY_PAGE_TITLE = "개인정보처리방침"

# ---------------------------------------------------------------------------
# Misc / a11y
# ---------------------------------------------------------------------------

NAV_HOME = "홈"
ALT_LOGO = ""  # decorative
