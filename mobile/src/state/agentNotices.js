const notifiedMeetingSuggestionIds = new Set();
let pendingAgentNotice = null;

export function filterNewMeetingSuggestions(suggestions = []) {
  return suggestions.filter((item) => {
    const id = String(item?.id || '');
    if (!id || notifiedMeetingSuggestionIds.has(id)) return false;
    notifiedMeetingSuggestionIds.add(id);
    return true;
  });
}

export function setPendingAgentNotice(text) {
  pendingAgentNotice = text;
}

export function takePendingAgentNotice() {
  const notice = pendingAgentNotice;
  pendingAgentNotice = null;
  return notice;
}
