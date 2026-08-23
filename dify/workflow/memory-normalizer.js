function main(input) {
  var raw = String((input && input.query) || "").trim();
  var normalized = raw.toLowerCase();
  var activeIntent = String((input && input.active_intent) || "");
  var pendingAction = String((input && input.pending_action) || "");
  var candidate = String((input && input.case_id_candidate) || "").trim().toUpperCase();
  var confirmed = String((input && input.confirmed_case_id) || "").trim().toUpperCase();
  var currentTurn = Number((input && input.dialog_count) || 0);
  var confirmedTurn = Number((input && input.last_case_confirmed_turn) || 0);
  var recent = [];

  try {
    var parsed = JSON.parse(String((input && input.recent_case_ids) || "[]"));
    if (Array.isArray(parsed)) {
      recent = parsed.map(function (item) {
        return String(item).toUpperCase();
      });
    }
  } catch (error) {
    recent = [];
  }

  var caseMatch = raw.match(/\b[A-Za-z]\d{8}\b/);
  var ticketMatch = raw.match(/\b(?:(?:TKT|WO)[-_]?[A-Za-z0-9]+|T\d{8})\b/i);
  var explicitCase = caseMatch ? caseMatch[0].toUpperCase() : "";
  var faultToken = (raw.match(/\b(?:ERR(?:400|401|403|404|409|429|500)|TIMEOUT)\b/i) || [""])[0].toUpperCase();
  var faultMode = faultToken === "TIMEOUT" ? "timeout" :
    (faultToken ? "http_" + faultToken.slice(3) : "");
  var asksOther = /(另一个|其他|换一个).{0,6}病例/.test(raw);
  var refersPrevious = /(刚刚|刚才|之前|上面).{0,5}(那个|提到的)?病例|那个病例/.test(raw);
  var memoryFresh = Boolean(confirmed) && currentTurn - confirmedTurn <= 10;
  var recentCandidates = recent.filter(function (item, index, values) {
    return item && values.indexOf(item) === index;
  });
  var caseId = explicitCase;
  var referenceStatus = "none";
  var isContinuation = false;

  if (!caseId && !asksOther && refersPrevious && memoryFresh) {
    if (recentCandidates.length > 1) {
      referenceStatus = "ambiguous";
    } else {
      caseId = recentCandidates[0] || confirmed;
      referenceStatus = "resolved";
      isContinuation = true;
    }
  }

  if (!caseId && !asksOther && referenceStatus !== "ambiguous" &&
      (pendingAction === "collect_case_id" || activeIntent === "case_status")) {
    caseId = candidate || (memoryFresh ? confirmed : "");
    isContinuation = Boolean(caseId);
  }

  var statusHint = /(病例|进度|状态|生产|发货|到哪|排产|方案|佩戴|完成)/.test(raw) ||
    activeIntent === "case_status";
  var needsCaseId = statusHint && !caseId;
  var riskWords = [
    "疼痛", "剧痛", "出血", "肿胀", "过敏", "呼吸困难", "吞咽困难",
    "脱落", "误吞", "发热", "感染", "临床异常"
  ];
  var hits = riskWords.filter(function (word) {
    return raw.indexOf(word) >= 0;
  });
  var riskHit = hits.length > 0;
  var nextTurn = currentTurn + 1;
  var nextRecent = recentCandidates.slice(-3);

  if (explicitCase) {
    nextRecent = nextRecent.filter(function (item) {
      return item !== explicitCase;
    });
    nextRecent.push(explicitCase);
    nextRecent = nextRecent.slice(-3);
  } else if (asksOther || !memoryFresh) {
    nextRecent = [];
  }

  return {
    query_norm: normalized,
    case_id: caseId,
    ticket_id: ticketMatch ? ticketMatch[0].toUpperCase() : "",
    risk_hit: riskHit,
    risk_reason: riskHit ? "命中高风险关键词：" + hits.join("、") : "",
    status_query_hint: statusHint,
    matched_keywords: hits.join(","),
    needs_case_id: needsCaseId,
    is_task_continuation: isContinuation,
    next_action: riskHit ? "handoff" : (needsCaseId ? "collect_case_id" : ""),
    fault_mode: faultMode,
    case_reference_status_next: referenceStatus,
    recent_case_ids_next: JSON.stringify(nextRecent),
    next_turn: nextTurn
  };
}
