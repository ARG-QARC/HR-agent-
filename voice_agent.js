/**
 * voice_agent.js - Dedicated AI Voice Recruiting Assistant Engine
 * Modularized separate file for continuous voice commands, intent parsing,
 * persistent conversation memory, text-to-speech, and background resume monitor.
 *
 * IMPORTANT: this file uses `import`/`export`, so it MUST be loaded as an
 * ES module from your HTML:
 *
 *     <script type="module" src="voice_agent.js"></script>
 *
 * Loading it as a plain <script src="..."> (no type="module") will throw a
 * SyntaxError on the import line above and silently stop the whole script
 * from running - which is why buttons wired up at the bottom (btn-send-voice-text,
 * btn-master-voice, btn-toggle-tts, btn-clear-chat) would do nothing.
 * Also note: type="module" scripts need to be served over http(s)://,
 * not opened directly as a file:// path, or the import will be blocked by CORS.
 */

import {
  getSetting, setSetting,
  getAllJobs, addJob, addCandidate,
  getCandidatesByJob, updateCandidate,
  getChatHistory, saveChatMessage, clearChatHistory
} from './db.js?v=6';

function getApiBaseUrl() {
  if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") {
    return "http://127.0.0.1:8000";
  }
  return window.location.origin;
}

// No hardcoded fallback key - shipping a real API key in client-side JS
// exposes it to anyone who opens DevTools. Store it via setSetting() from
// a settings UI instead, and call your own backend if you need it kept secret.

// ── Agent State ──────────────────────────────────────────────────────────────
export let workflowState = {
  activeJob: null,
  candidates: [],
  currentStep: 1,
  ttsEnabled: true,
  isMasterListening: false,
  speechRecognition: null,
  // LinkedIn auto-post workflow flags
  awaitingLinkedInConfirm: false,   // True when waiting for user to confirm they posted on LinkedIn
  pendingPipelineResume: false      // True when RUN_FULL_PIPELINE is paused waiting for LinkedIn action
};

// ── System Intelligence & Architectural Context Prompt Builder ─────────────
export async function getSystemIntelligencePrompt(customRole = "Autonomous Recruiter AI Assistant") {
  const companyName = await getSetting("COMPANY_NAME", "Al Rahim Group");
  const companyIntro = await getSetting("COMPANY_INTRO", "A leading business conglomerate specializing in global trade, engineering, and manufacturing.");
  const contactEmail = await getSetting("CONTACT_EMAIL", "danish.alrahimgroup@gmail.com");

  const activeJob = workflowState.activeJob;
  const activeJobContext = activeJob
    ? `Active Target Position Context: "${activeJob.title}" (Job ID: ${activeJob.job_id}, Subject Tag: ${activeJob.subject_tag || 'N/A'})`
    : "Active Target Position Context: No position selected currently.";

  return `SYSTEM ARCHITECTURE & IDENTITY OVERVIEW:
You are 'RecruiterAI', an autonomous, highly intelligent AI Corporate Recruiting Agent operating inside the 'RecruiterAI Automated Agent' system.

ENVIRONMENT & SYSTEM ARCHITECTURE:
- Operating Platform: Standalone Progressive Web App (PWA) client running in device memory (IndexedDB) with direct cloud AI orchestration.
- Local Storage Memory: Browser IndexedDB ('LinkedInAssistantDB'). Stores jobs, candidate profiles, evaluation metrics, and persistent chat logs directly on the user's device.
- Active Integration Modules: Real-time microphone Web Audio Speech-to-Text, client-side PDF resume parsing (pdf.js), Gmail IMAP candidate resume ingestion, automated SMTP email interview scheduling, and Google Gemini AI API via HTTPS.

ORGANIZATIONAL CONTEXT:
- Organization: ${companyName}
- Corporate Profile: ${companyIntro}
- Recruiting Contact Email: ${contactEmail}
- ${activeJobContext}

CORE WORKFLOW RESPONSIBILITIES & INTELLIGENCE:
1. Job Description & LinkedIn Post Generation: Transform raw user prompts/voice instructions into high-impact, professional LinkedIn recruiting posts and structured Job Descriptions with clear application tags.
2. Candidate Application Ingestion: Parse PDF resumes and email text bodies synced from Gmail IMAP or user PDF uploads.
3. Multi-Dimensional Candidate Scoring: Evaluate candidates across 5 core metrics: Relevance (0-100), Technical Skills, Relevant Experience, Education, and Location. Provide actionable recommendations (Strong Hire / Hire / Consider / Reject), key strengths, and skill gaps.
4. End-to-End Recruitment Pipeline Automation: Seamlessly guide recruiters across the 5 pipeline steps:
   - Step 1: Job Post Creation & Requirement Definition
   - Step 2: Applicant Ingestion & PDF Text Extraction
   - Step 3: Multi-Dimensional AI Candidate Scoring
   - Step 4: Top Applicant Selection & Ranking
   - Step 5: Automated Interview Invitation & Email Delivery
5. Assigned Specialization: ${customRole}

OPERATIONAL INSTRUCTIONS:
- Always respond with high authority, professionalism, and concise actionable insights tailored specifically to the recruiter operating within this PWA environment.`;
}

// ── Gemini REST API Helper ───────────────────────────────────────────────────
export async function callGeminiAPI(contents, systemInstruction = "") {
  let apiKey = await getSetting("GEMINI_API_KEY", "");
  
  if (!apiKey || !apiKey.trim()) {
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/settings`);
      if (res.ok) {
        const remoteSettings = await res.json();
        if (remoteSettings.GEMINI_API_KEY) {
          apiKey = remoteSettings.GEMINI_API_KEY;
          await setSetting("GEMINI_API_KEY", apiKey);
        }
      }
    } catch (e) {
      console.warn("Backend settings sync notice:", e);
    }
  }

  if (!apiKey || !apiKey.trim()) {
    throw new Error("No Gemini API key configured. Please enter your Google AI Studio key in Cloud & Settings tab or .env file.");
  }

  const models = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-1.5-flash"
  ];
  let errors = [];

  for (const model of models) {
    try {
      const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey.trim()}`;

      const payload = { contents };
      if (systemInstruction) {
        payload.systemInstruction = { parts: [{ text: systemInstruction }] };
      }

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 15000);

      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal
      }).finally(() => clearTimeout(timeoutId));

      if (!response.ok) {
        const errJson = await response.json().catch(() => ({}));
        throw new Error(`[${model}] HTTP ${response.status}: ${errJson.error?.message || response.statusText}`);
      }

      const data = await response.json();
      const text = data.candidates?.[0]?.content?.parts?.[0]?.text;
      if (text) {
        return text.trim();
      }
    } catch (err) {
      console.warn(`Gemini call error with ${model}:`, err.message);
      errors.push(`${model}: ${err.message}`);
    }
  }

  throw new Error(`All Gemini models failed. Details: ${errors.join(" | ")}`);
}

// ── UI Context Updates ───────────────────────────────────────────────────────
export function setPipelineStep(stepNum) {
  workflowState.currentStep = stepNum;
  const steps = [
    { id: "step-1-draft", num: 1 },
    { id: "step-2-job", num: 2 },
    { id: "step-3-resumes", num: 3 },
    { id: "step-4-scored", num: 4 },
    { id: "step-5-interview", num: 5 }
  ];

  steps.forEach(s => {
    const el = document.getElementById(s.id);
    if (!el) return;
    el.classList.remove("active", "completed");
    if (s.num < stepNum) el.classList.add("completed");
    else if (s.num === stepNum) el.classList.add("active");
  });
}

export function updateAgentContextUI() {
  const contextEl = document.getElementById("agent-context-text");
  if (!contextEl) return;

  if (workflowState.activeJob) {
    const candCount = workflowState.candidates ? workflowState.candidates.length : 0;
    contextEl.innerText = `Active Position: "${workflowState.activeJob.title}" (ID: ${workflowState.activeJob.job_id}) | ${candCount} candidates loaded.`;
  } else {
    contextEl.innerText = 'No active job position selected yet. Dictate or type a query to begin!';
  }
}

// ── Text-To-Speech (TTS) ─────────────────────────────────────────────────────
export function speakText(text) {
  if (!workflowState.ttsEnabled || !('speechSynthesis' in window)) return;
  try {
    window.speechSynthesis.cancel();
    const cleanText = text.replace(/<[^>]*>/g, '').replace(/[^\w\s.,!?-]/g, '');
    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.rate = 1.0;
    utterance.pitch = 1.0;

    const orb = document.getElementById("agent-voice-orb");
    if (orb) orb.classList.add("speaking");

    utterance.onend = () => {
      if (orb) orb.classList.remove("speaking");
    };
    utterance.onerror = () => {
      if (orb) orb.classList.remove("speaking");
    };
    window.speechSynthesis.speak(utterance);
  } catch (err) {
    console.warn("Speech Synthesis error:", err);
  }
}

// ── Chat Stream Renderer ─────────────────────────────────────────────────────
export function addAgentChatMessage(sender, text, saveToDb = true) {
  const chatStream = document.getElementById("agent-chat-stream");
  if (!chatStream) return;

  const msgDiv = document.createElement("div");
  msgDiv.className = `chat-msg ${sender.toLowerCase()}`;

  const authorSpan = document.createElement("span");
  authorSpan.className = "msg-author";
  authorSpan.innerText = sender === "user" ? "👤 You:" : (sender === "system" ? "🤖 Recruiter AI:" : "⚡ Recruiter Agent:");

  const textDiv = document.createElement("div");
  textDiv.className = "msg-text";
  textDiv.innerHTML = text;

  msgDiv.appendChild(authorSpan);
  msgDiv.appendChild(textDiv);
  chatStream.appendChild(msgDiv);
  chatStream.scrollTop = chatStream.scrollHeight;

  if (saveToDb && sender !== "system") {
    saveChatMessage(sender, text).catch(e => console.warn(e));
  }
}

export async function loadPersistedChatHistory() {
  try {
    const history = await getChatHistory();
    if (history && history.length > 0) {
      for (const item of history) {
        addAgentChatMessage(item.sender, item.text, false);
      }
    }
  } catch (e) {
    console.warn("Could not load chat history:", e);
  }
}

// ── Candidate AI Scoring Client-Side ─────────────────────────────────────────
export async function scoreCandidateClientSide(job, candidate) {
  const prompt = `Evaluate candidate for job:
Job Title: ${job.title}
Job Description: ${job.description}

Candidate Name: ${candidate.name}
Resume Text: ${candidate.parsed_text || candidate.summary || ''}
Email Body: ${candidate.email_body || ''}

Return ONLY a valid JSON object matching:
{
  "relevance_score": 85,
  "skills_score": 80,
  "experience_score": 85,
  "education_score": 90,
  "location_score": 80,
  "recommendation": "Strong Hire",
  "strengths": ["Strong Python background", "Data engineering skills"],
  "gaps": ["Location relocation required"],
  "summary": "High potential candidate with relevant experience."
}`;

  try {
    const systemPrompt = await getSystemIntelligencePrompt("Multi-Dimensional Candidate Evaluation Specialist");
    const responseText = await callGeminiAPI(
      [{ parts: [{ text: prompt }] }],
      systemPrompt
    );

    const match = responseText.match(/\{[\s\S]*\}/);
    const parsed = JSON.parse(match ? match[0] : responseText);

    return {
      relevance_score: parsed.relevance_score || 80,
      skills_score: parsed.skills_score || 80,
      experience_score: parsed.experience_score || 80,
      education_score: parsed.education_score || 80,
      location_score: parsed.location_score || 80,
      recommendation: parsed.recommendation || "Strong Hire",
      strengths: Array.isArray(parsed.strengths) ? parsed.strengths.join("\n• ") : String(parsed.strengths || ""),
      gaps: Array.isArray(parsed.gaps) ? parsed.gaps.join("\n• ") : String(parsed.gaps || ""),
      summary: parsed.summary || "Evaluated by Gemini AI.",
      status: "Scored"
    };
  } catch (err) {
    console.error("Client side candidate scoring error:", err);
    return {
      relevance_score: 75,
      recommendation: "Hire",
      summary: "Evaluated via fallback scoring.",
      status: "Scored"
    };
  }
}

// ── LLM Noise Cleaner & Intent Classifier ───────────────────────────────────
export async function cleanTranscriptAndDetectIntent(rawTranscript) {
  const companyName = await getSetting("COMPANY_NAME", "Al Rahim Group");
  const contactEmail = await getSetting("CONTACT_EMAIL", "danish.alrahimgroup@gmail.com");

  const prompt = `This is a raw speech-to-text transcript captured from the user's microphone in a live recruiting environment. It may contain background noise artifacts, acoustic transcription errors, filler words (um, ah, like, you know), or fragmented syntax.

Raw Voice Transcript: "${rawTranscript}"

Task:
1. Filter out background noise, filler words, and acoustic transcription errors to get the true user intent.
2. Determine the user's intent: "CREATE_POST" | "SCORE_CANDIDATES" | "SCHEDULE_INTERVIEW" | "FETCH_RESUMES" | "STATUS" | "CHAT" | "RUN_FULL_PIPELINE".
3. IF the user is asking to create, post, or draft a job position (or providing job role/requirements):
   - Extract the exact, clean official Job Title (e.g. "Senior Data Scientist").
   - Generate a complete, professional, structured Job Description and engaging LinkedIn post incorporating all user-specified requirements, skills, experience level, and responsibilities.
   - Include apply instructions: "Send resume to ${contactEmail} with Subject containing 'ARG-[Job-Title]'".
4. Return ONLY a valid JSON object with NO markdown wrapping, matching this exact schema:
{
  "cleaned_text": "Cleaned user request without filler words or acoustic errors",
  "intent": "CREATE_POST" | "SCORE_CANDIDATES" | "SCHEDULE_INTERVIEW" | "FETCH_RESUMES" | "STATUS" | "CHAT" | "RUN_FULL_PIPELINE",
  "job_title": "Extracted Official Job Title (if applicable)",
  "job_description": "Full generated Job Description with headline, requirements, emojis, and apply tag instructions (if intent is CREATE_POST)"
}`;

  try {
    const systemPrompt = await getSystemIntelligencePrompt("Acoustic Speech Cleaner, Intent Classifier & Job Architect Specialist");
    const resText = await callGeminiAPI(
      [{ parts: [{ text: prompt }] }],
      systemPrompt
    );
    const match = resText.match(/\{[\s\S]*\}/);
    if (match) {
      return JSON.parse(match[0]);
    }
  } catch (e) {
    console.warn("LLM Transcript Cleaning & Job Extraction notice:", e.message);
    return { cleaned_text: rawTranscript, intent: null, job_title: null, job_description: null, error: e.message };
  }
  return { cleaned_text: rawTranscript, intent: null, job_title: null, job_description: null };
}

// ── Query Intent Processor & Engine ──────────────────────────────────────────
export async function processVoiceAgentQuery(userQuery) {
  if (!userQuery || !userQuery.trim()) return;
  const query = userQuery.trim();

  // 1. Immediately render User message in UI
  addAgentChatMessage("user", query, false);
  saveChatMessage("user", query).catch(e => console.warn(e));

  // ── LinkedIn Post Confirmation Detection ──────────────────────────────────
  // If the agent is waiting for the user to confirm they've posted on LinkedIn,
  // intercept confirmation phrases and resume the workflow before running
  // through the full LLM intent classification pipeline.
  const lowerQueryCheck = query.toLowerCase();
  if (workflowState.awaitingLinkedInConfirm &&
    (lowerQueryCheck.includes("posted") || lowerQueryCheck.includes("done") ||
     lowerQueryCheck.includes("published") || lowerQueryCheck.includes("shared") ||
     lowerQueryCheck.includes("i posted") || lowerQueryCheck.includes("it's posted") ||
     lowerQueryCheck.includes("post is live") || lowerQueryCheck.includes("already posted"))) {
    workflowState.awaitingLinkedInConfirm = false;

    // If the full pipeline was paused at Step 1-2, resume it from Step 3
    if (workflowState.pendingPipelineResume) {
      workflowState.pendingPipelineResume = false;
      addAgentChatMessage("ai",
        `🎉 Great! Your job post is now live on LinkedIn. Resuming the full recruitment pipeline from <b>Step 3: Fetch Resumes</b>...`);
      speakText("Excellent! Your LinkedIn post is live. Resuming the recruitment pipeline.");
      // Trigger pipeline resume from Step 3 onwards
      await _resumePipelineFromStep3();
      return;
    }

    // Standard confirmation — just acknowledge and let the user proceed manually
    addAgentChatMessage("ai",
      `🎉 Great! Your job post is now live on LinkedIn. Continuing recruitment workflow — say <i>"Score candidates"</i> or <i>"Fetch resumes"</i> to proceed!`);
    speakText("Excellent! Your LinkedIn post is live. Ready to continue the recruitment pipeline.");
    return;
  }

  // 2. Immediately render AI thinking indicator
  addAgentChatMessage("ai", "<i>🤖 Filtering noise & analyzing request...</i>", false);

  // 3. Run LLM Noise Cleaner & Intent Classifier
  const llmAnalysis = await cleanTranscriptAndDetectIntent(query);
  const cleanedQuery = llmAnalysis.cleaned_text || query;

  const lowerQuery = cleanedQuery.toLowerCase();
  let intent = llmAnalysis.intent || "CREATE_POST";

  if (!llmAnalysis.intent) {
    if (lowerQuery.includes("full pipeline") || lowerQuery.includes("run automation") || lowerQuery.includes("automate everything") || lowerQuery.includes("do everything") || lowerQuery.includes("end to end")) {
      intent = "RUN_FULL_PIPELINE";
    } else if (lowerQuery.includes("fetch") || lowerQuery.includes("sync") || lowerQuery.includes("download") || lowerQuery.includes("gmail")) {
      intent = "FETCH_RESUMES";
    } else if (lowerQuery.includes("score") || lowerQuery.includes("evaluate") || lowerQuery.includes("applicant") || (lowerQuery.includes("resume") && !lowerQuery.includes("fetch"))) {
      intent = "SCORE_CANDIDATES";
    } else if (lowerQuery.includes("interview") || lowerQuery.includes("schedule") || (lowerQuery.includes("call") && lowerQuery.includes("interview"))) {
      intent = "SCHEDULE_INTERVIEW";
    } else if (lowerQuery.includes("status") || lowerQuery.includes("how many") || lowerQuery.includes("list")) {
      intent = "STATUS";
    } else if (!(lowerQuery.includes("post") || lowerQuery.includes("job") || lowerQuery.includes("hire") || lowerQuery.includes("hiring") || lowerQuery.includes("looking for") || lowerQuery.includes("generate") || lowerQuery.includes("create") || lowerQuery.includes("developer") || lowerQuery.includes("engineer") || lowerQuery.includes("scientist") || lowerQuery.includes("analyst") || lowerQuery.includes("manager") || lowerQuery.includes("designer") || lowerQuery.includes("experience") || lowerQuery.includes("exp") || lowerQuery.includes("years") || lowerQuery.includes("requirement") || lowerQuery.includes("need"))) {
      intent = "CHAT";
    }
  }

  const removeThinkingIndicator = () => {
    const chatStream = document.getElementById("agent-chat-stream");
    if (!chatStream) return;
    const msgs = chatStream.querySelectorAll(".chat-msg");
    msgs.forEach(m => {
      if (m.innerText.includes("Thinking and executing")) {
        m.remove();
      }
    });
  };

  try {
    if (intent === "CREATE_POST") {
      let extractedTitle = llmAnalysis.job_title || query
        .replace(/generate a post for|create a post for|draft post for|we are hiring a|looking for a|hire a|create post|new job|we need a|we require a/gi, '')
        .replace(/at our company|he must be|she must be|with experience|for our team|years experience|years exp|skills/gi, '')
        .trim();

      if (!extractedTitle || extractedTitle.length < 3) {
        extractedTitle = "Specialist Role";
      }
      extractedTitle = extractedTitle.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');

      const companyName = await getSetting("COMPANY_NAME", "Al Rahim Group");
      const contactEmail = await getSetting("CONTACT_EMAIL", "danish.alrahimgroup@gmail.com");
      const subjectTag = `ARG-${extractedTitle.replace(/\s+/g, '-')}`;

      let generatedPost = llmAnalysis.job_description || "";

      if (!generatedPost || generatedPost.length < 20) {
        try {
          const systemPrompt = await getSystemIntelligencePrompt("Executive Job Description & LinkedIn Recruiting Strategist");
          generatedPost = await callGeminiAPI(
            [{ parts: [{ text: `Generate a comprehensive Job Description and engaging LinkedIn post for the following requirements: "${query}".` }] }],
            `${systemPrompt}

SPECIAL TASK:
As soon as the recruiter specifies job requirements, immediately generate a complete, structured, professional Job Description & LinkedIn Post. Include:
1. 🚀 Headline & Role Summary
2. 🎯 Key Responsibilities & Skill Requirements (bullet points with emojis)
3. 💼 Experience Level & Benefits
4. 📬 Application Instructions: "Send resume to ${contactEmail} with Subject: '${subjectTag}'"

Make it ready for instant candidate resume matching.`
          );
        } catch (geminiErr) {
          console.warn("Gemini call error fallback:", geminiErr.message);
          addAgentChatMessage("system", `⚠️ <b>AI Intelligence Warning:</b> Could not reach Gemini API (${geminiErr.message}). Displaying local template fallback. Please verify your GEMINI_API_KEY in Cloud & Settings.`);
          generatedPost = `🚀 WE ARE HIRING: ${extractedTitle.toUpperCase()} at ${companyName}!\n\nWe are seeking a qualified ${extractedTitle} to join our growing corporate team.\n\nRequirements & Details:\n• ${query}\n• Strong corporate background and analytical expertise\n• Excellent teamwork and communication skills\n\n👉 TO APPLY: Send your resume to ${contactEmail} with subject line containing '${subjectTag}'.`;
        }
      }

      removeThinkingIndicator();

      const job_id = `ARG-JD-${Date.now().toString().slice(-4)}`;
      const newJob = {
        job_id,
        title: extractedTitle,
        description: generatedPost,
        subject_tag: subjectTag,
        created_at: new Date().toISOString()
      };

      await addJob(newJob).catch(e => console.warn(e));
      workflowState.activeJob = newJob;
      workflowState.candidates = [];

      updateAgentContextUI();
      setPipelineStep(2);
      if (typeof window.refreshJobsUI === "function") {
        await window.refreshJobsUI().catch(e => console.warn(e));
      }

      // Build the unique button ID suffix to prevent clashes with previous messages
      const btnSuffix = Date.now();

      // Escape the generated post for safe embedding in a data attribute
      const escapedPost = generatedPost.replace(/"/g, '&quot;').replace(/'/g, '&#39;');

      const replyMsg = `✅ Generated and saved job position post for <b>${extractedTitle}</b> (ID: ${job_id}) to device memory!\n\n<pre style="white-space: pre-wrap; background: rgba(15,23,42,0.7); padding: 12px; border-radius: 8px; margin-top: 8px; font-family: inherit; font-size: 13px; border: 1px solid rgba(56,189,248,0.2);">${generatedPost}</pre>\n\n<div class="linkedin-action-btns" id="linkedin-btns-${btnSuffix}"><button class="btn-linkedin-post" onclick="window.postToLinkedIn('${btnSuffix}')" id="btn-li-post-${btnSuffix}">🔗 Post to LinkedIn</button><button class="btn-copy-continue" onclick="window.copyAndContinue('${btnSuffix}')" id="btn-li-copy-${btnSuffix}">📋 Copy & Continue</button></div>`;

      // Store the post data on the window so the button handlers can access it
      window[`_liPostData_${btnSuffix}`] = {
        postText: generatedPost,
        jobTitle: extractedTitle,
        isPipeline: false
      };

      addAgentChatMessage("ai", replyMsg);
      speakText(`Generated and saved job position post for ${extractedTitle}. You can post it to LinkedIn or copy it to clipboard.`);

    } else if (intent === "SCORE_CANDIDATES") {
      removeThinkingIndicator();
      if (!workflowState.activeJob) {
        const jobs = await getAllJobs();
        if (jobs.length > 0) workflowState.activeJob = jobs[0];
      }

      if (!workflowState.activeJob) {
        const msg = "Please state a job position to create first before scoring candidates.";
        addAgentChatMessage("ai", msg);
        speakText(msg);
        return;
      }

      let cands = await getCandidatesByJob(workflowState.activeJob.job_id);

      if (cands.length === 0) {
        addAgentChatMessage("ai", "⚡ <i>No candidate resumes found in device memory yet. Automatically checking Gmail for newly submitted candidate emails...</i>");
        speakText("Checking Gmail for newly submitted candidate emails.");

        try {
          const localJobs = await getAllJobs();
          for (const j of localJobs) {
            await fetch(`${getApiBaseUrl()}/api/jobs`, {
              method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(j)
            }).catch(() => null);
          }
          const syncRes = await fetch(`${getApiBaseUrl()}/api/sync-resumes`, { method: "POST" }).catch(() => null);
          if (syncRes && syncRes.ok) {
            for (const j of localJobs) {
              const candRes = await fetch(`${getApiBaseUrl()}/api/candidates/${j.job_id}`).catch(() => null);
              if (candRes && candRes.ok) {
                const remoteCands = await candRes.json();
                for (const c of remoteCands) {
                  await addCandidate({
                    job_id: c.job_id, name: c.name, email: c.email,
                    resume_name: c.resume_path ? c.resume_path.split('\\').pop().split('/').pop() : `${c.name}.pdf`,
                    parsed_text: c.parsed_text, relevance_score: c.relevance_score,
                    skills_score: c.skills_score, experience_score: c.experience_score,
                    education_score: c.education_score, location_score: c.location_score,
                    recommendation: c.recommendation, strengths: c.strengths ? c.strengths.split('\n') : [],
                    gaps: c.gaps ? c.gaps.split('\n') : [], summary: c.summary
                  });
                }
              }
            }
          }
        } catch (e) {
          console.warn("Real-time auto-sync notice:", e);
        }

        cands = await getCandidatesByJob(workflowState.activeJob.job_id);
      }

      workflowState.candidates = cands;

      if (cands.length === 0) {
        const msg = `No candidate resumes found for <b>${workflowState.activeJob.title}</b> in device memory yet. Upload candidate PDFs in <b>Jobs & Resumes</b> tab to proceed.`;
        addAgentChatMessage("ai", msg);
        speakText(`No candidate resumes found for ${workflowState.activeJob.title}. Please upload candidate PDFs.`);
        return;
      }

      addAgentChatMessage("ai", `<i>Evaluating ${cands.length} candidates for ${workflowState.activeJob.title} using multi-dimensional AI scoring...</i>`);

      for (const cand of cands) {
        if (!cand.relevance_score) {
          const evalRes = await scoreCandidateClientSide(workflowState.activeJob, cand);
          Object.assign(cand, evalRes);
          await updateCandidate(cand);
        }
      }

      const updatedCands = await getCandidatesByJob(workflowState.activeJob.job_id);
      workflowState.candidates = updatedCands.sort((a, b) => (b.relevance_score || 0) - (a.relevance_score || 0));
      updateAgentContextUI();
      setPipelineStep(4);

      const topCand = workflowState.candidates[0];
      const replyMsg = `Successfully evaluated candidates for <b>${workflowState.activeJob.title}</b>! Top candidate: <b>${topCand.name}</b> with score <b>${topCand.relevance_score}/100</b>. Say <i>"Schedule interview with top candidate"</i> to proceed!`;
      addAgentChatMessage("ai", replyMsg);
      speakText(`Evaluated candidates for ${workflowState.activeJob.title}. Top candidate is ${topCand.name}.`);

    } else if (intent === "SCHEDULE_INTERVIEW") {
      removeThinkingIndicator();
      if (!workflowState.activeJob) {
        const jobs = await getAllJobs();
        if (jobs.length > 0) workflowState.activeJob = jobs[0];
      }

      const cands = workflowState.activeJob ? await getCandidatesByJob(workflowState.activeJob.job_id) : [];
      if (cands.length === 0) {
        const msg = "No candidates available to schedule an interview for.";
        addAgentChatMessage("ai", msg);
        speakText(msg);
        return;
      }

      const topCand = cands.sort((a, b) => (b.relevance_score || 0) - (a.relevance_score || 0))[0];
      const modal = document.getElementById("interview-modal");
      if (modal) {
        const compName = await getSetting("COMPANY_NAME", "Al Rahim Group");
        document.getElementById("interview-cand-id").value = topCand.candidate_id || '';
        document.getElementById("interview-cand-name").value = topCand.name || 'Candidate';
        document.getElementById("interview-cand-email").value = topCand.email || '';
        document.getElementById("interview-notes").value = `Invitation for ${workflowState.activeJob ? workflowState.activeJob.title : 'Position'} at ${compName}.\nMatch Score: ${topCand.relevance_score || 90}%`;
        modal.style.display = "flex";
      }
      setPipelineStep(5);

      const replyMsg = `Opened interview invitation dialog for candidate <b>${topCand.name}</b> (${topCand.email || 'No email'}). Review details and click 'Send Interview Call Email'.`;
      addAgentChatMessage("ai", replyMsg);
      speakText(`Opened interview invitation dialog for ${topCand.name}.`);

    } else if (intent === "FETCH_RESUMES") {
      removeThinkingIndicator();
      addAgentChatMessage("ai", `<i>📥 Step 3: Fetching resumes from Gmail and syncing to device memory...</i>`);
      setPipelineStep(3);

      let syncCount = 0;
      let scoredCount = 0;
      let localJobs = [];
      try {
        const baseUrl = getApiBaseUrl();
        localJobs = await getAllJobs();
        for (const j of localJobs) {
          await fetch(`${baseUrl}/api/jobs`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(j)
          }).catch(() => null);
        }

        const response = await fetch(`${baseUrl}/api/sync-resumes`, { method: "POST" }).catch(() => null);
        if (response && response.ok) {
          const data = await response.json();
          syncCount = data.synced_count || 0;
          scoredCount = data.scored_count || 0;

          for (const j of localJobs) {
            const candRes = await fetch(`${baseUrl}/api/candidates/${j.job_id}`).catch(() => null);
            if (candRes && candRes.ok) {
              const remoteCands = await candRes.json();
              for (const c of remoteCands) {
                await addCandidate({
                  job_id: c.job_id,
                  name: c.name,
                  email: c.email,
                  resume_name: c.resume_path ? c.resume_path.split('\\').pop().split('/').pop() : `${c.name}.pdf`,
                  parsed_text: c.parsed_text,
                  relevance_score: c.relevance_score,
                  skills_score: c.skills_score,
                  experience_score: c.experience_score,
                  education_score: c.education_score,
                  location_score: c.location_score,
                  recommendation: c.recommendation,
                  strengths: c.strengths ? c.strengths.split('\n') : [],
                  gaps: c.gaps ? c.gaps.split('\n') : [],
                  summary: c.summary,
                  status: c.status,
                  applied_at: c.applied_at || new Date().toISOString()
                });
              }
            }
          }
        } else {
          console.warn("[VoiceAgent] Backend sync endpoint unavailable. Running in local PWA mode.");
        }

        if (!workflowState.activeJob && localJobs.length > 0) {
          workflowState.activeJob = localJobs[0];
        }
        if (workflowState.activeJob) {
          workflowState.candidates = await getCandidatesByJob(workflowState.activeJob.job_id);
        }
        updateAgentContextUI();
        if (typeof window.refreshJobsUI === "function") await window.refreshJobsUI().catch(() => { });

        const replyMsg = `✅ Fetched <b>${syncCount}</b> resume(s) from Gmail. Backend auto-scored <b>${scoredCount}</b>. Say <i>"Score candidates"</i> or <i>"Schedule interview"</i> to continue.`;
        addAgentChatMessage("ai", replyMsg);
        speakText(`Fetched ${syncCount} resumes from Gmail.`);
        if (scoredCount > 0) setPipelineStep(4);
      } catch (err) {
        addAgentChatMessage("ai", `📱 Operating in standalone PWA mode using device memory.`);
        speakText("Operating in standalone PWA mode.");
      }

    } else if (intent === "RUN_FULL_PIPELINE") {
      removeThinkingIndicator();
      addAgentChatMessage("ai", `<i>⚡ Running full recruitment pipeline: Post → Fetch → Score → Interview...</i>`);
      setPipelineStep(1);

      const companyName = await getSetting("COMPANY_NAME", "Al Rahim Group");
      const contactEmail = await getSetting("CONTACT_EMAIL", "danish.alrahimgroup@gmail.com");

      // Step 1+2: Create job post if none active
      if (!workflowState.activeJob) {
        let extractedTitle = llmAnalysis.job_title || query
          .replace(/full pipeline|run automation|automate everything|do everything|end to end|generate a post for|create a post for|draft post for|we are hiring a|looking for a|hire a|create post|new job/gi, '')
          .replace(/at our company|he must be|she must be|with experience|for our team/gi, '')
          .trim();
        if (!extractedTitle || extractedTitle.length < 3) extractedTitle = "Business Analyst";
        extractedTitle = extractedTitle.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
        const subjectTag = `ARG-${extractedTitle.replace(/\s+/g, '-')}`;

        let generatedPost = llmAnalysis.job_description || "";
        if (!generatedPost || generatedPost.length < 20) {
          try {
            generatedPost = await callGeminiAPI(
              [{ parts: [{ text: `Draft an engaging, professional LinkedIn job post for: "${query}".` }] }],
              `You are a top corporate recruiter for '${companyName}'. Write a structured, engaging LinkedIn post with bullet points and emojis. End with apply email: ${contactEmail} and subject tag '${subjectTag}'.`
            );
          } catch (geminiErr) {
            generatedPost = `🚀 WE ARE HIRING: ${extractedTitle.toUpperCase()} at ${companyName}!\n\n👉 TO APPLY: Send your resume to ${contactEmail} with subject line containing '${subjectTag}'.`;
          }
        }

        const job_id = `ARG-JD-${Date.now().toString().slice(-4)}`;
        const newJob = { job_id, title: extractedTitle, description: generatedPost, subject_tag: subjectTag, created_at: new Date().toISOString() };
        await addJob(newJob).catch(e => console.warn(e));
        workflowState.activeJob = newJob;
        workflowState.candidates = [];
        addAgentChatMessage("system", `⚡ <b>Pipeline Step 1-2:</b> Created job post for <b>${extractedTitle}</b>.`);
      }
      setPipelineStep(2);
      updateAgentContextUI();
      if (typeof window.refreshJobsUI === "function") await window.refreshJobsUI().catch(() => { });

      // ── Pipeline Pause: Show LinkedIn action buttons ──────────────────────
      // Pause the pipeline here so the user can post to LinkedIn before
      // proceeding to Step 3 (Fetch resumes). The pipeline will resume when
      // the user clicks "Copy & Continue" or confirms they posted.
      const pipelineBtnSuffix = Date.now();
      const pipelineEscapedPost = (workflowState.activeJob.description || "").replace(/"/g, '&quot;').replace(/'/g, '&#39;');

      window[`_liPostData_${pipelineBtnSuffix}`] = {
        postText: workflowState.activeJob.description || "",
        jobTitle: workflowState.activeJob.title || "Job Position",
        isPipeline: true
      };

      const pipelinePostMsg = `📝 Job post ready for <b>${workflowState.activeJob.title}</b>:\n\n<pre style="white-space: pre-wrap; background: rgba(15,23,42,0.7); padding: 12px; border-radius: 8px; margin-top: 8px; font-family: inherit; font-size: 13px; border: 1px solid rgba(56,189,248,0.2);">${workflowState.activeJob.description}</pre>\n\n<div class="linkedin-action-btns" id="linkedin-btns-${pipelineBtnSuffix}"><button class="btn-linkedin-post" onclick="window.postToLinkedIn('${pipelineBtnSuffix}')" id="btn-li-post-${pipelineBtnSuffix}">🔗 Post to LinkedIn</button><button class="btn-copy-continue" onclick="window.copyAndContinue('${pipelineBtnSuffix}')" id="btn-li-copy-${pipelineBtnSuffix}">📋 Copy & Continue Pipeline</button></div>`;

      addAgentChatMessage("ai", pipelinePostMsg);
      speakText(`Job post ready for ${workflowState.activeJob.title}. Post to LinkedIn or copy and continue the pipeline.`);
      // Stop pipeline execution here — it will be resumed by the button handlers
      return;

      // Step 3: Fetch resumes
      addAgentChatMessage("system", "⚡ <b>Pipeline Step 3:</b> Fetching email resumes...");
      setPipelineStep(3);
      try {
        const baseUrl = getApiBaseUrl();
        const localJobs = await getAllJobs();
        for (const j of localJobs) {
          await fetch(`${baseUrl}/api/jobs`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(j)
          }).catch(() => null);
        }
        const syncRes = await fetch(`${baseUrl}/api/sync-resumes`, { method: "POST" }).catch(() => null);
        if (syncRes && syncRes.ok) {
          const syncData = await syncRes.json();
          addAgentChatMessage("system", `⚡ Fetched ${syncData.synced_count || 0} resume(s) from Gmail.`);
          for (const j of localJobs) {
            const candRes = await fetch(`${baseUrl}/api/candidates/${j.job_id}`).catch(() => null);
            if (candRes && candRes.ok) {
              const remoteCands = await candRes.json();
              for (const c of remoteCands) {
                await addCandidate({
                  job_id: c.job_id, name: c.name, email: c.email,
                  resume_name: c.resume_path ? c.resume_path.split('\\').pop().split('/').pop() : `${c.name}.pdf`,
                  parsed_text: c.parsed_text, relevance_score: c.relevance_score,
                  skills_score: c.skills_score, experience_score: c.experience_score,
                  education_score: c.education_score, location_score: c.location_score,
                  recommendation: c.recommendation,
                  strengths: c.strengths ? c.strengths.split('\n') : [],
                  gaps: c.gaps ? c.gaps.split('\n') : [],
                  summary: c.summary, status: c.status,
                  applied_at: c.applied_at || new Date().toISOString()
                });
              }
            }
          }
        } else {
          addAgentChatMessage("system", "📱 Operating in standalone PWA mode using local device memory.");
        }
      } catch (e) {
        addAgentChatMessage("system", "📱 Operating in standalone PWA mode using local device memory.");
      }

      // Step 4: Score candidates
      addAgentChatMessage("system", "⚡ <b>Pipeline Step 4:</b> Scoring candidates...");
      setPipelineStep(4);
      const cands = workflowState.activeJob ? await getCandidatesByJob(workflowState.activeJob.job_id) : [];
      for (const cand of cands) {
        if (!cand.relevance_score) {
          const evalRes = await scoreCandidateClientSide(workflowState.activeJob, cand);
          Object.assign(cand, evalRes);
          await updateCandidate(cand);
        }
      }
      workflowState.candidates = (await getCandidatesByJob(workflowState.activeJob.job_id))
        .sort((a, b) => (b.relevance_score || 0) - (a.relevance_score || 0));
      updateAgentContextUI();
      if (typeof window.refreshJobsUI === "function") await window.refreshJobsUI().catch(() => { });

      if (workflowState.candidates.length === 0) {
        addAgentChatMessage("ai", "Pipeline paused: no candidates found. Upload PDFs or configure Gmail sync, then say <i>\"Score candidates\"</i>.");
        return;
      }

      // Step 5: Open interview for top candidate
      addAgentChatMessage("system", "⚡ <b>Pipeline Step 5:</b> Opening interview invitation for top candidate...");
      setPipelineStep(5);
      const topCand = workflowState.candidates[0];
      const modal = document.getElementById("interview-modal");
      if (modal) {
        const compName = await getSetting("COMPANY_NAME", "Al Rahim Group");
        document.getElementById("interview-cand-id").value = topCand.candidate_id || '';
        document.getElementById("interview-cand-name").value = topCand.name || 'Candidate';
        document.getElementById("interview-cand-email").value = topCand.email || '';
        document.getElementById("interview-notes").value = `Invitation for ${workflowState.activeJob.title} at ${compName}.\nMatch Score: ${topCand.relevance_score || 90}%`;
        modal.style.display = "flex";
      }

      const finalMsg = `🎉 <b>Full pipeline complete!</b> Top candidate: <b>${topCand.name}</b> (${topCand.relevance_score}/100). Review the interview dialog and click <b>Send Interview Call Email</b> to finish.`;
      addAgentChatMessage("ai", finalMsg);
      speakText(`Full pipeline complete. Top candidate is ${topCand.name}. Review and send the interview email.`);

    } else if (intent === "STATUS") {
      removeThinkingIndicator();
      const jobs = await getAllJobs();
      const replyMsg = `Currently tracking <b>${jobs.length}</b> job positions in device memory. Active job: <b>${workflowState.activeJob ? workflowState.activeJob.title : 'None selected'}</b>.`;
      addAgentChatMessage("ai", replyMsg);
      speakText(`Currently tracking ${jobs.length} job positions in device memory.`);

    } else {
      let replyMsg = "";
      try {
        const systemPrompt = await getSystemIntelligencePrompt("Continuous Voice Assistant & HR Strategist");
        replyMsg = await callGeminiAPI(
          [{ parts: [{ text: query }] }],
          systemPrompt
        );
      } catch (e) {
        replyMsg = `I received your request: "${query}". Active position context: ${workflowState.activeJob ? workflowState.activeJob.title : 'None'}. Say "Create post for [Title]" to generate a job post!`;
      }
      removeThinkingIndicator();
      addAgentChatMessage("ai", replyMsg);
      speakText(replyMsg);
    }

  } catch (err) {
    console.error("Voice Agent error:", err);
    removeThinkingIndicator();
    addAgentChatMessage("ai", `❌ Voice Assistant Note: ${err.message}`);
    speakText("Completed processing your query.");
  }
}

// ── Global Window Handlers ────────────────────────────────────────────────────
window.sendVoiceAgentQuery = function () {
  const vInput = document.getElementById("voice-text-input");
  const pInput = document.getElementById("prompt-input");

  let q = vInput ? vInput.value.trim() : "";
  if (!q && pInput) {
    q = pInput.value.trim();
  }

  if (!q) return;

  if (vInput) vInput.value = "";
  if (pInput) pInput.value = "";

  processVoiceAgentQuery(q);
};

window.toggleTTSVoice = function () {
  workflowState.ttsEnabled = !workflowState.ttsEnabled;
  const ttsIcon = document.getElementById("tts-icon");
  if (ttsIcon) ttsIcon.innerText = workflowState.ttsEnabled ? "🔊" : "🔇";
  alert(`Voice audio feedback ${workflowState.ttsEnabled ? "enabled" : "muted"}.`);
};

window.clearAgentChatMemory = async function () {
  if (confirm("Reset conversation memory from device storage?")) {
    await clearChatHistory();
    const chatStream = document.getElementById("agent-chat-stream");
    if (chatStream) {
      chatStream.innerHTML = `
        <div class="chat-msg system">
          <span class="msg-author">🤖 Recruiter AI:</span>
          <div class="msg-text">Conversation memory reset. Type or dictate your next request!</div>
        </div>`;
    }
  }
};

// ── LinkedIn Auto-Post Window Handlers ────────────────────────────────────────
// These functions are called by the inline action buttons rendered in chat
// messages after a job post is generated. They are attached to the window
// object so they can be invoked from onclick attributes in dynamic HTML.

/**
 * Disables both LinkedIn action buttons in the chat message to prevent
 * duplicate clicks after the user has already chosen an action.
 *
 * @param {string} btnSuffix - The unique timestamp suffix identifying the button pair.
 */
function _disableLinkedInButtons(btnSuffix) {
  const postBtn = document.getElementById(`btn-li-post-${btnSuffix}`);
  const copyBtn = document.getElementById(`btn-li-copy-${btnSuffix}`);
  if (postBtn) postBtn.disabled = true;
  if (copyBtn) copyBtn.disabled = true;
}

/**
 * Posts the generated job content to LinkedIn by calling the backend automation
 * API endpoint. The backend opens the LinkedIn desktop app, navigates to the
 * "Start a post" editor, and pastes the content. The user must manually click
 * the final "Post" button on LinkedIn.
 *
 * If the backend is unreachable (e.g., mobile PWA, no local server), falls back
 * to copying the post to the clipboard with an instructional message.
 *
 * @param {string} btnSuffix - The unique timestamp suffix used to retrieve stored post data.
 */
window.postToLinkedIn = async function (btnSuffix) {
  const postData = window[`_liPostData_${btnSuffix}`];
  if (!postData) {
    addAgentChatMessage("ai", "⚠️ Post data not found. Please try generating the post again.");
    return;
  }

  // Disable buttons immediately to prevent duplicate clicks
  _disableLinkedInButtons(btnSuffix);

  // Show loading state on the LinkedIn button
  const postBtn = document.getElementById(`btn-li-post-${btnSuffix}`);
  if (postBtn) {
    postBtn.classList.add("btn-linkedin-loading");
    postBtn.innerHTML = "🔗 Opening LinkedIn...";
  }

  addAgentChatMessage("system", "⚡ <i>Opening LinkedIn app and pasting your post content...</i>");
  speakText("Opening LinkedIn to post your job description.");

  try {
    // Call the backend LinkedIn auto-post API endpoint
    const res = await fetch(`${getApiBaseUrl()}/api/linkedin-post`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        post_text: postData.postText,
        job_title: postData.jobTitle
      })
    });

    if (res.ok) {
      const data = await res.json();

      if (data.status === "success") {
        // Full success: LinkedIn app is open with content pasted in the editor
        addAgentChatMessage("ai",
          `✅ ${data.message}\n\n👆 Review your post on LinkedIn desktop app and click the <b>Post</b> button when ready.\n\nOnce posted, say <i>"I posted it"</i> or <i>"Done"</i> to continue the recruitment pipeline.`);
        speakText("Post content is ready in LinkedIn desktop app. Review and click Post when you're satisfied.");
      } else {
        // Partial success or app URI fallback: trigger desktop app launch via protocol scheme
        try {
          await navigator.clipboard.writeText(postData.postText);
        } catch (clipErr) { }
        window.location.href = "linkedin://";
        addAgentChatMessage("ai",
          `📋 Post content copied to clipboard! Launching LinkedIn Desktop app...\n\nPress <b>Ctrl+V</b> inside LinkedIn app to paste. Say <i>"I posted it"</i> or <i>"Done"</i> after posting.`);
        speakText("Post copied to clipboard. Launching LinkedIn desktop app.");
      }

      // Set state to await LinkedIn confirmation from the user
      workflowState.awaitingLinkedInConfirm = true;
      if (postData.isPipeline) {
        workflowState.pendingPipelineResume = true;
      }
    } else {
      // Backend returned an error status code — fall back to desktop app URI launch
      throw new Error(`Server returned ${res.status}`);
    }
  } catch (err) {
    console.warn("[LinkedIn Post] Launching desktop app via URI protocol notice:", err.message);

    // Fallback: copy to clipboard and trigger native LinkedIn desktop app protocol
    try {
      await navigator.clipboard.writeText(postData.postText);
    } catch (clipErr) { }

    try {
      window.location.href = "linkedin://";
      addAgentChatMessage("ai",
        `📋 Job post copied to clipboard! Launching LinkedIn Desktop app...\n\nPress <b>Ctrl+V</b> in the LinkedIn app to paste your post. Say <i>"I posted it"</i> or <i>"Done"</i> after posting.`);
      speakText("Post copied to clipboard. Launching LinkedIn desktop app.");
    } catch (launchErr) {
      addAgentChatMessage("ai",
        `📋 Job post copied to clipboard! Please open your LinkedIn Desktop app and press <b>Ctrl+V</b> to paste your post.\n\nSay <i>"I posted it"</i> or <i>"Done"</i> after posting.`);
    }

    workflowState.awaitingLinkedInConfirm = true;
    if (postData.isPipeline) {
      workflowState.pendingPipelineResume = true;
    }
  }

  // Remove loading state
  if (postBtn) {
    postBtn.classList.remove("btn-linkedin-loading");
    postBtn.innerHTML = "✅ LinkedIn Opened";
  }

  // Clean up stored post data
  delete window[`_liPostData_${btnSuffix}`];
};

/**
 * Copies the generated post text to the system clipboard and continues the
 * workflow immediately. If this was triggered during a RUN_FULL_PIPELINE,
 * the pipeline is resumed from Step 3 (Fetch resumes).
 *
 * @param {string} btnSuffix - The unique timestamp suffix used to retrieve stored post data.
 */
window.copyAndContinue = async function (btnSuffix) {
  const postData = window[`_liPostData_${btnSuffix}`];
  if (!postData) {
    addAgentChatMessage("ai", "⚠️ Post data not found. Please try generating the post again.");
    return;
  }

  // Disable buttons immediately to prevent duplicate clicks
  _disableLinkedInButtons(btnSuffix);

  // Copy post text to clipboard
  try {
    await navigator.clipboard.writeText(postData.postText);
  } catch (err) {
    console.warn("[Copy & Continue] Clipboard write failed:", err);
  }

  // Clean up stored post data
  delete window[`_liPostData_${btnSuffix}`];

  if (postData.isPipeline) {
    // Pipeline mode: acknowledge and resume from Step 3 immediately
    addAgentChatMessage("ai",
      `📋 Post copied to clipboard! Paste it on LinkedIn whenever you're ready.\n\n⚡ <i>Resuming full pipeline from Step 3: Fetch Resumes...</i>`);
    speakText("Post copied to clipboard. Resuming the recruitment pipeline.");
    await _resumePipelineFromStep3();
  } else {
    // Standalone CREATE_POST mode: acknowledge and let user proceed manually
    addAgentChatMessage("ai",
      `📋 Post copied to clipboard! Paste it on LinkedIn or any platform whenever you're ready.\n\nContinuing workflow — say <i>"Score candidates"</i> or <i>"Fetch resumes"</i> to proceed!`);
    speakText("Post copied to clipboard. Ready to continue.");
  }
};

/**
 * Resumes the RUN_FULL_PIPELINE from Step 3 onwards after the user has
 * either posted to LinkedIn or chosen to copy and continue.
 *
 * This is an internal function that replicates the pipeline logic from
 * Step 3 (Fetch resumes) through Step 5 (Interview invitation), which
 * was previously inline in the RUN_FULL_PIPELINE handler.
 */
async function _resumePipelineFromStep3() {
  // Step 3: Fetch resumes from Gmail via backend
  addAgentChatMessage("system", "⚡ <b>Pipeline Step 3:</b> Fetching email resumes...");
  setPipelineStep(3);
  try {
    const baseUrl = getApiBaseUrl();
    const localJobs = await getAllJobs();
    for (const j of localJobs) {
      await fetch(`${baseUrl}/api/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(j)
      }).catch(() => null);
    }
    const syncRes = await fetch(`${baseUrl}/api/sync-resumes`, { method: "POST" }).catch(() => null);
    if (syncRes && syncRes.ok) {
      const syncData = await syncRes.json();
      addAgentChatMessage("system", `⚡ Fetched ${syncData.synced_count || 0} resume(s) from Gmail.`);
      for (const j of localJobs) {
        const candRes = await fetch(`${baseUrl}/api/candidates/${j.job_id}`).catch(() => null);
        if (candRes && candRes.ok) {
          const remoteCands = await candRes.json();
          for (const c of remoteCands) {
            await addCandidate({
              job_id: c.job_id, name: c.name, email: c.email,
              resume_name: c.resume_path ? c.resume_path.split('\\').pop().split('/').pop() : `${c.name}.pdf`,
              parsed_text: c.parsed_text, relevance_score: c.relevance_score,
              skills_score: c.skills_score, experience_score: c.experience_score,
              education_score: c.education_score, location_score: c.location_score,
              recommendation: c.recommendation,
              strengths: c.strengths ? c.strengths.split('\n') : [],
              gaps: c.gaps ? c.gaps.split('\n') : [],
              summary: c.summary, status: c.status,
              applied_at: c.applied_at || new Date().toISOString()
            });
          }
        }
      }
    } else {
      addAgentChatMessage("system", "📱 Operating in standalone PWA mode using local device memory.");
    }
  } catch (e) {
    addAgentChatMessage("system", "📱 Operating in standalone PWA mode using local device memory.");
  }

  // Step 4: Score candidates using multi-dimensional AI evaluation
  addAgentChatMessage("system", "⚡ <b>Pipeline Step 4:</b> Scoring candidates...");
  setPipelineStep(4);
  const cands = workflowState.activeJob ? await getCandidatesByJob(workflowState.activeJob.job_id) : [];
  for (const cand of cands) {
    if (!cand.relevance_score) {
      const evalRes = await scoreCandidateClientSide(workflowState.activeJob, cand);
      Object.assign(cand, evalRes);
      await updateCandidate(cand);
    }
  }
  workflowState.candidates = (await getCandidatesByJob(workflowState.activeJob.job_id))
    .sort((a, b) => (b.relevance_score || 0) - (a.relevance_score || 0));
  updateAgentContextUI();
  if (typeof window.refreshJobsUI === "function") await window.refreshJobsUI().catch(() => { });

  if (workflowState.candidates.length === 0) {
    addAgentChatMessage("ai", "Pipeline paused: no candidates found. Upload PDFs or configure Gmail sync, then say <i>\"Score candidates\"</i>.");
    return;
  }

  // Step 5: Open interview invitation dialog for the top-ranked candidate
  addAgentChatMessage("system", "⚡ <b>Pipeline Step 5:</b> Opening interview invitation for top candidate...");
  setPipelineStep(5);
  const topCand = workflowState.candidates[0];
  const modal = document.getElementById("interview-modal");
  if (modal) {
    const compName = await getSetting("COMPANY_NAME", "Al Rahim Group");
    document.getElementById("interview-cand-id").value = topCand.candidate_id || '';
    document.getElementById("interview-cand-name").value = topCand.name || 'Candidate';
    document.getElementById("interview-cand-email").value = topCand.email || '';
    document.getElementById("interview-notes").value = `Invitation for ${workflowState.activeJob.title} at ${compName}.\nMatch Score: ${topCand.relevance_score || 90}%`;
    modal.style.display = "flex";
  }

  const finalMsg = `🎉 <b>Full pipeline complete!</b> Top candidate: <b>${topCand.name}</b> (${topCand.relevance_score}/100). Review the interview dialog and click <b>Send Interview Call Email</b> to finish.`;
  addAgentChatMessage("ai", finalMsg);
  speakText(`Full pipeline complete. Top candidate is ${topCand.name}. Review and send the interview email.`);
}

let accumulatedSpeechTranscript = "";

window.startVoiceDictation = async function () {
  const masterBtn = document.getElementById("btn-master-voice");
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  // Request browser hardware DSP noise cancellation stream
  try {
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });
    }
  } catch (audioErr) {
    console.warn("Hardware noise cancellation notice:", audioErr.message);
  }

  if (SpeechRecognition) {
    try {
      if (!workflowState.speechRecognition) {
        const recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = "en-US";

        recognition.onstart = () => {
          workflowState.isMasterListening = true;
          if (masterBtn) masterBtn.classList.add("listening");
          const label = document.getElementById("master-voice-label");
          if (label) label.innerText = "Listening... Press to Stop & Submit";
          const orb = document.getElementById("agent-voice-orb");
          if (orb) orb.classList.add("listening");
        };

        recognition.onresult = (event) => {
          let currentTranscript = "";
          for (let i = 0; i < event.results.length; i++) {
            currentTranscript += event.results[i][0].transcript + " ";
          }
          accumulatedSpeechTranscript = currentTranscript.trim();

          const inputEl = document.getElementById("agent-voice-input");
          if (inputEl) {
            inputEl.value = accumulatedSpeechTranscript;
          }
        };

        recognition.onerror = (e) => {
          console.warn("Speech recognition error notice:", e.error);
          if (e.error === 'no-speech' && workflowState.isMasterListening) {
            return;
          }
        };

        recognition.onend = () => {
          if (workflowState.isMasterListening) {
            try {
              recognition.start();
              return;
            } catch (err) {
              console.warn("Speech restart notice:", err.message);
            }
          }

          workflowState.isMasterListening = false;
          if (masterBtn) masterBtn.classList.remove("listening");
          const label = document.getElementById("master-voice-label");
          if (label) label.innerText = "Dictate Voice";
          const orb = document.getElementById("agent-voice-orb");
          if (orb) orb.classList.remove("listening");

          if (accumulatedSpeechTranscript && accumulatedSpeechTranscript.trim()) {
            const finalQuery = accumulatedSpeechTranscript.trim();
            accumulatedSpeechTranscript = "";
            processVoiceAgentQuery(finalQuery);
          }
        };

        workflowState.speechRecognition = recognition;
      }

      if (workflowState.isMasterListening) {
        workflowState.isMasterListening = false;
        workflowState.speechRecognition.stop();
      } else {
        accumulatedSpeechTranscript = "";
        workflowState.isMasterListening = true;
        workflowState.speechRecognition.start();
      }
    } catch (e) {
      console.warn("Speech start error:", e);
      const fallback = prompt("Type your voice query for automated agent:");
      if (fallback) processVoiceAgentQuery(fallback);
    }
  } else {
    const q = prompt("Type your voice query for automated agent:");
    if (q) processVoiceAgentQuery(q);
  }
};

export function initBackgroundResumeMonitor() {
  const clearBtn = document.getElementById("btn-clear-chat");
  if (clearBtn) {
    clearBtn.addEventListener("click", window.clearAgentChatMemory);
  }

  // Periodic Background Resume Monitoring
  setInterval(async () => {
    if (!workflowState.activeJob) return;

    try {
      const candidates = await getCandidatesByJob(workflowState.activeJob.job_id);
      const unscored = candidates.filter(c => !c.relevance_score || c.status === "Applied");

      if (unscored.length > 0) {
        addAgentChatMessage("system", `⚡ <b>Background Agent:</b> Found ${unscored.length} newly fetched applicant(s) for <b>${workflowState.activeJob.title}</b>. Automatically evaluating...`);
        speakText(`Background agent evaluating ${unscored.length} new applicants.`);

        for (const cand of unscored) {
          const evalRes = await scoreCandidateClientSide(workflowState.activeJob, cand);
          Object.assign(cand, evalRes);
          await updateCandidate(cand);

          const updateMsg = `⚡ <b>Background Agent Log:</b> Evaluated applicant <b>${cand.name}</b> (${cand.email || 'Direct Upload'}). Match Score: <b>${cand.relevance_score}/100</b> - Recommendation: <b>${cand.recommendation}</b>.`;
          addAgentChatMessage("system", updateMsg);
          speakText(`Evaluated applicant ${cand.name}. Match score: ${cand.relevance_score} out of 100.`);
        }

        workflowState.candidates = await getCandidatesByJob(workflowState.activeJob.job_id);
        updateAgentContextUI();
        setPipelineStep(4);
      }
    } catch (err) {
      console.warn("Background resume monitor error:", err);
    }
  }, 15000);
}

// ── Auto Initialization on Load ─────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  console.log("[voice_agent.js] module loaded and DOMContentLoaded fired.");
  const expectedButtonIds = ["btn-send-voice-text", "btn-master-voice", "btn-toggle-tts", "btn-clear-chat"];
  expectedButtonIds.forEach(id => {
    if (!document.getElementById(id)) {
      console.warn(`[voice_agent.js] Expected button #${id} was not found in the DOM.`);
    }
  });

  try { await loadPersistedChatHistory(); } catch (e) { }
  try { initBackgroundResumeMonitor(); } catch (e) { }

  try {
    const jobs = await getAllJobs();
    if (jobs.length > 0) {
      workflowState.activeJob = jobs[0];
      workflowState.candidates = await getCandidatesByJob(jobs[0].job_id);
      updateAgentContextUI();
    }
  } catch (e) { }
});

// Event Delegation Fallback
document.addEventListener("click", (e) => {
  const btn = e.target.closest("button");
  if (!btn) return;
  if (btn.id === "btn-send-voice-text") {
    e.preventDefault();
    window.sendVoiceAgentQuery();
  } else if (btn.id === "btn-master-voice") {
    e.preventDefault();
    window.startVoiceDictation();
  } else if (btn.id === "btn-toggle-tts") {
    e.preventDefault();
    window.toggleTTSVoice();
  } else if (btn.id === "btn-clear-chat") {
    e.preventDefault();
    window.clearAgentChatMemory();
  }
});