const GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models/";
const SCRIPT_VERSION = "gemini-policy-chatbot-2026-04-17-v6";

function doGet() {
  return jsonResponse({
    ok: true,
    version: SCRIPT_VERSION,
    provider: "gemini"
  });
}

function doPost(e) {
  try {
    const payload = JSON.parse((e.postData && e.postData.contents) || "{}");
    const idToken = String(payload.idToken || "");
    const question = String(payload.question || "").trim();
    const policies = Array.isArray(payload.policies) ? payload.policies : [];

    if (!idToken) {
      return jsonResponse({ error: "missing_id_token" });
    }
    if (!question) {
      return jsonResponse({ error: "missing_question" });
    }
    if (!policies.length) {
      return jsonResponse({ answer: "저장된 회칙 데이터가 없습니다.", evidence: [] });
    }

    verifyFirebaseUser(idToken);
    return jsonResponse(askGeminiOnce(question, policies));
  } catch (error) {
    const message = String(error && error.message ? error.message : error);
    return jsonResponse({
      answer: "챗봇 처리 중 오류가 발생했습니다: " + message,
      evidence: [],
      error: message,
      version: SCRIPT_VERSION
    });
  }
}

function verifyFirebaseUser(idToken) {
  const firebaseApiKey = PropertiesService.getScriptProperties().getProperty("FIREBASE_WEB_API_KEY");
  if (!firebaseApiKey) {
    throw new Error("FIREBASE_WEB_API_KEY script property is missing.");
  }

  const response = UrlFetchApp.fetch(
    "https://identitytoolkit.googleapis.com/v1/accounts:lookup?key=" + encodeURIComponent(firebaseApiKey),
    {
      method: "post",
      contentType: "application/json",
      payload: JSON.stringify({ idToken: idToken }),
      muteHttpExceptions: true
    }
  );

  if (response.getResponseCode() >= 300) {
    throw new Error("Firebase login token could not be verified: " + response.getContentText());
  }

  const body = JSON.parse(response.getContentText() || "{}");
  if (!body.users || !body.users.length) {
    throw new Error("Firebase login token is invalid.");
  }
  return body.users[0];
}

function askGeminiOnce(question, policies) {
  const apiKey = PropertiesService.getScriptProperties().getProperty("GEMINI_API_KEY");
  const model = PropertiesService.getScriptProperties().getProperty("GEMINI_CHAT_MODEL") || "gemini-2.5-flash";
  const fallbackModel =
    PropertiesService.getScriptProperties().getProperty("GEMINI_FALLBACK_MODEL") || "gemini-2.5-flash-lite";
  const thinkingBudget = Number(PropertiesService.getScriptProperties().getProperty("GEMINI_THINKING_BUDGET") || "0");

  if (!apiKey) {
    throw new Error("GEMINI_API_KEY script property is missing.");
  }

  const prompt = buildPrompt(question, policies);
  const generationConfig = {
    temperature: 0,
    responseMimeType: "application/json",
    responseSchema: {
      type: "object",
      properties: {
        answer: {
          type: "string"
        },
        evidence: {
          type: "array",
          items: {
            type: "object",
            properties: {
              section: { type: "string" },
              article: { type: "string" },
              clause: { type: "string" },
              paragraph: { type: "string" }
            },
            required: ["section", "article", "paragraph"]
          }
        }
      },
      required: ["answer", "evidence"]
    },
    maxOutputTokens: 1200
  };

  if (!Number.isNaN(thinkingBudget) && thinkingBudget >= 0) {
    generationConfig.thinkingConfig = {
      thinkingBudget: thinkingBudget
    };
  }

  const response = fetchGeminiWithRetry({
    apiKey: apiKey,
    model: model,
    fallbackModel: fallbackModel,
    prompt: prompt,
    generationConfig: generationConfig
  });

  return parseGeminiResponse(response.getContentText(), question, policies);
}

function parseGeminiResponse(bodyText, question, policies) {
  try {
    const body = JSON.parse(bodyText || "{}");
    const outputText = extractGeminiText(body);
    const parsed = parseModelJson(outputText);
    return normalizeChatbotResult({
      answer: String(parsed.answer || "").trim() || "챗봇 응답을 읽지 못했습니다. 다시 한 번 질문해 주세요.",
      evidence: Array.isArray(parsed.evidence) ? parsed.evidence : [],
      version: SCRIPT_VERSION,
      parseError: parsed.parseError || ""
    }, question, policies);
  } catch (error) {
    return {
      answer: "챗봇 응답 형식을 정리하지 못했습니다. 다시 한 번 질문해 주세요.",
      evidence: [],
      error: "Gemini response parse failed: " + String(error && error.message ? error.message : error),
      version: SCRIPT_VERSION
    };
  }
}

function fetchGeminiWithRetry(options) {
  const models = [options.model];
  if (options.fallbackModel && options.fallbackModel !== options.model) {
    models.push(options.fallbackModel);
  }

  let lastError = "";
  for (let modelIndex = 0; modelIndex < models.length; modelIndex += 1) {
    const model = models[modelIndex];
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const response = fetchGeminiModel({
        apiKey: options.apiKey,
        model: model,
        prompt: options.prompt,
        generationConfig: options.generationConfig
      });
      const status = response.getResponseCode();
      const bodyText = response.getContentText();

      if (status < 300) {
        return response;
      }

      lastError = "Gemini API failed on " + model + ": " + bodyText;
      if (![429, 500, 502, 503, 504].includes(status)) {
        throw new Error(lastError);
      }

      Utilities.sleep(Math.pow(2, attempt) * 800);
    }
  }

  throw new Error(lastError);
}

function fetchGeminiModel(options) {
  return UrlFetchApp.fetch(
    GEMINI_API_BASE + encodeURIComponent(options.model) + ":generateContent",
    {
      method: "post",
      contentType: "application/json",
      headers: {
        "x-goog-api-key": options.apiKey
      },
      payload: JSON.stringify({
        systemInstruction: {
          parts: [
            {
              text: [
                "당신은 TTPAA 회칙 전용 검증 보조자입니다.",
                "제공된 policy JSON 배열만 근거로 답하세요.",
                "근거가 부족하면 회칙에서 확인할 수 없다고 답하세요.",
                "answer는 사용자가 쉽게 이해하도록 Markdown 형식으로 작성하세요.",
                "answer에는 적절한 이모티콘, 짧은 제목, 줄바꿈, bullet list를 사용할 수 있습니다.",
                "Markdown은 반드시 JSON 문자열 안에 안전하게 escape해서 넣으세요.",
                "단, evidence는 기존 JSON 배열 형식을 그대로 유지하세요.",
                "회칙에서 답을 찾은 경우 evidence 배열은 절대로 비우지 마세요.",
                "evidence를 비우는 경우 answer에는 회칙에서 확인할 수 없다고만 답하세요.",
                "반드시 JSON만 반환하세요."
              ].join(" ")
            }
          ]
        },
        contents: [
          {
            role: "user",
            parts: [
              {
                text: options.prompt
              }
            ]
          }
        ],
        generationConfig: options.generationConfig
      }),
      muteHttpExceptions: true
    }
  );
}

function buildPrompt(question, policies) {
  return [
    "질문:",
    question,
    "",
    "반환 JSON 스키마:",
    '{"answer":"한국어 답변","evidence":[{"section":"","article":"","clause":"","paragraph":""}]}',
    "",
    "근거 제시 규칙:",
    "- answer는 policy JSON 배열에서 확인 가능한 내용만 사용합니다.",
    "- answer는 Markdown 문자열로 작성합니다.",
    "- answer의 줄바꿈은 JSON 문자열 안에서 \\n으로 escape되어야 합니다.",
    "- answer 안에서 큰따옴표를 꼭 써야 하면 JSON 문자열에 맞게 escape합니다.",
    "- answer에는 이해를 돕는 이모티콘을 자연스럽게 1~3개 정도 사용할 수 있습니다.",
    "- answer는 짧은 제목, 요약, 핵심 근거, 주의할 점 순서처럼 읽기 쉽게 줄바꿈합니다.",
    "- answer 안에 회칙 원문 전체를 길게 반복하지 말고 요지를 설명합니다.",
    "- evidence에는 답변에 직접 사용한 조항만 넣습니다.",
    "- evidence 항목에는 section, article, clause, paragraph를 포함합니다.",
    "- 회칙에서 답을 찾았다면 evidence는 반드시 1개 이상 넣습니다.",
    "- 질문과 관련된 조항이 없을 때만 evidence를 빈 배열로 두고 answer에 회칙에서 확인할 수 없다고 씁니다.",
    "",
    "policy JSON:",
    JSON.stringify(policies)
  ].join("\n");
}

function extractGeminiText(responseBody) {
  const parts =
    (((responseBody.candidates || [])[0] || {}).content || {}).parts || [];
  return parts
    .map(function (part) {
      return part.text || "";
    })
    .join("\n")
    .trim();
}

function normalizeChatbotResult(result, question, policies) {
  const normalized = {
    answer: result.answer,
    evidence: normalizeEvidence(result.evidence, policies),
    version: result.version || SCRIPT_VERSION,
    parseError: result.parseError || "",
    error: result.error || ""
  };

  if (!normalized.evidence.length && shouldHaveEvidence(normalized.answer)) {
    normalized.evidence = fallbackEvidence(question + "\n" + normalized.answer, policies);
  }

  return normalized;
}

function normalizeEvidence(evidence, policies) {
  const items = Array.isArray(evidence) ? evidence : [];
  const normalized = [];
  const seen = {};

  items.forEach(function (item) {
    const hydrated = hydrateEvidence(item, policies);
    if (!hydrated.paragraph) {
      return;
    }

    const key = [hydrated.section, hydrated.article, hydrated.clause, hydrated.paragraph].join("|");
    if (seen[key]) {
      return;
    }
    seen[key] = true;
    normalized.push(hydrated);
  });

  return normalized.slice(0, 3);
}

function hydrateEvidence(item, policies) {
  const section = String(item && item.section ? item.section : "").trim();
  const article = String(item && item.article ? item.article : "").trim();
  const clause = String(item && item.clause ? item.clause : "").trim();
  const paragraph = String(item && item.paragraph ? item.paragraph : "").trim();

  const exact = policies.find(function (policy) {
    return String(policy.paragraph || "").trim() === paragraph;
  });
  if (exact) {
    return evidenceFromPolicy(exact);
  }

  const byLocation = policies.find(function (policy) {
    return (!section || policy.section === section)
      && (!article || policy.article === article)
      && (!clause || policy.clause === clause);
  });
  if (byLocation) {
    return evidenceFromPolicy(byLocation);
  }

  return {
    section: section,
    article: article,
    clause: clause,
    paragraph: paragraph
  };
}

function fallbackEvidence(seedText, policies) {
  const terms = importantTerms(seedText);
  if (!terms.length) {
    return [];
  }

  return policies
    .map(function (policy) {
      const text = searchablePolicyText(policy);
      const compactText = text.replace(/\s+/g, "");
      let score = 0;
      terms.forEach(function (term) {
        if (text.indexOf(term) >= 0) {
          score += Math.min(term.length, 8);
        }
        if (compactText.indexOf(term.replace(/\s+/g, "")) >= 0) {
          score += Math.min(term.length, 8);
        }
      });
      return { policy: policy, score: score };
    })
    .filter(function (entry) {
      return entry.score > 0;
    })
    .sort(function (a, b) {
      return b.score - a.score;
    })
    .slice(0, 3)
    .map(function (entry) {
      return evidenceFromPolicy(entry.policy);
    });
}

function importantTerms(text) {
  const normalized = String(text || "")
    .replace(/[^\w가-힣\s]/g, " ")
    .split(/\s+/)
    .map(function (term) {
      return term.trim();
    })
    .filter(function (term) {
      return term.length >= 2 && !isStopword(term);
    });

  const seen = {};
  const terms = [];
  normalized.forEach(function (term) {
    if (!seen[term]) {
      seen[term] = true;
      terms.push(term);
    }
  });
  return terms.slice(0, 20);
}

function isStopword(term) {
  return [
    "회칙",
    "확인",
    "가능",
    "내용",
    "경우",
    "대한",
    "있습니다",
    "합니다",
    "됩니다",
    "그리고",
    "또는",
    "관련",
    "근거",
    "요약"
  ].indexOf(term) >= 0;
}

function searchablePolicyText(policy) {
  return [
    policy.section || "",
    policy.article || "",
    policy.clause || "",
    policy.subclause || "",
    policy.paragraph || ""
  ].join(" ");
}

function evidenceFromPolicy(policy) {
  return {
    section: String(policy.section || ""),
    article: String(policy.article || ""),
    clause: String(policy.clause || ""),
    paragraph: String(policy.paragraph || policy.text || "")
  };
}

function shouldHaveEvidence(answer) {
  const text = String(answer || "");
  if (!text.trim()) {
    return false;
  }
  return text.indexOf("확인할 수 없") < 0
    && text.indexOf("찾을 수 없") < 0
    && text.indexOf("응답 형식") < 0
    && text.indexOf("다시 한 번 질문") < 0;
}

function parseModelJson(text) {
  const trimmed = String(text || "").trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
  try {
    return JSON.parse(trimmed);
  } catch (error) {
    const match = trimmed.match(/\{[\s\S]*\}/);
    if (match) {
      try {
        return JSON.parse(match[0]);
      } catch (nestedError) {
        return repairBrokenJson(match[0], nestedError);
      }
    }
    return {
      answer: trimmed || "챗봇 응답을 읽지 못했습니다. 다시 한 번 질문해 주세요.",
      evidence: []
    };
  }
}

function repairBrokenJson(text, originalError) {
  const answerMatch = String(text || "").match(/"answer"\s*:\s*"([\s\S]*?)"\s*,\s*"evidence"\s*:/);
  const evidenceMatch = String(text || "").match(/"evidence"\s*:\s*(\[[\s\S]*\])\s*}/);
  const answer = answerMatch ? unescapeJsonFragment(answerMatch[1]) : "";

  if (evidenceMatch) {
    try {
      const evidence = JSON.parse(evidenceMatch[1]);
      return {
        answer: answer || "챗봇 응답 일부를 복구했습니다.",
        evidence: Array.isArray(evidence) ? evidence : [],
        parseError: String(originalError && originalError.message ? originalError.message : originalError)
      };
    } catch (error) {
      // Fall through to the safe response below.
    }
  }

  return {
    answer: answer || "챗봇 응답 형식을 정리하지 못했습니다. 다시 한 번 질문해 주세요.",
    evidence: [],
    parseError: String(originalError && originalError.message ? originalError.message : originalError)
  };
}

function unescapeJsonFragment(value) {
  try {
    return JSON.parse('"' + String(value || "").replace(/"/g, '\\"') + '"');
  } catch (error) {
    return String(value || "").replace(/\\n/g, "\n").replace(/\\"/g, '"');
  }
}

function jsonResponse(body) {
  return ContentService.createTextOutput(JSON.stringify(body)).setMimeType(ContentService.MimeType.JSON);
}
