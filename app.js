/**
 * app.js - Main Application Logic for Mobile PWA
 * Handles Gemini API requests, Voice Recording, PDF parsing, Candidate Multi-Dimensional AI Scoring, and UI state.
 */

import {
  getSetting, setSetting,
  getAllJobs, addJob, deleteJob,
  getCandidatesByJob, addCandidate, updateCandidate, deleteCandidate,
  exportDatabaseToJSON, importDatabaseFromJSON, syncToCloudStorage, syncFromCloudStorage,
  getChatHistory, saveChatMessage, clearChatHistory
} from './db.js?v=3';

import {
  workflowState,
  updateAgentContextUI
} from './voice_agent.js?v=3';

export function getApiBaseUrl() {
  if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") {
    return "http://127.0.0.1:8000";
  }
  return window.location.origin;
}

// Configure pdf.js worker URL
if (window.pdfjsLib) {
  window.pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
}

// ── Application State ────────────────────────────────────────────────────────
let state = {
  activeTab: 'tab-writer',
  isRecording: false,
  mediaRecorder: null,
  audioChunks: [],
  selectedJobId: '',
  geminiKey: '',
  companyName: '',
  companyIntro: '',
  contactEmail: ''
};

const DEFAULT_GEMINI_KEY = "";

async function callGeminiAPI(contents, systemInstruction = "") {
  let apiKey = state.geminiKey || await getSetting("GEMINI_API_KEY", DEFAULT_GEMINI_KEY);
  if (!apiKey || !apiKey.trim()) {
    throw new Error("Gemini API key is required. Please set GEMINI_API_KEY in Settings.");
  }

  const models = ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash-8b"];
  let lastError = null;

  for (const model of models) {
    try {
      const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey.trim()}`;
      
      const payload = { contents };
      if (systemInstruction) {
        payload.systemInstruction = { parts: [{ text: systemInstruction }] };
      }

      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

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
      lastError = err;
    }
  }

  throw lastError || new Error("All Gemini models failed.");
}

// ── Voice Dictation via Web Audio API ───────────────────────────────────────
async function initVoiceRecorder() {
  const micBtn = document.getElementById("btn-record");
  if (!micBtn) return;

  micBtn.addEventListener("click", async () => {
    if (!state.isRecording) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        state.audioChunks = [];
        state.mediaRecorder = new MediaRecorder(stream);
        
        state.mediaRecorder.ondataavailable = (e) => {
          if (e.data.size > 0) state.audioChunks.push(e.data);
        };

        state.mediaRecorder.onstop = async () => {
          const audioBlob = new Blob(state.audioChunks, { type: "audio/mp3" });
          micBtn.classList.remove("recording");
          micBtn.innerHTML = "<span>🎤</span> Processing Audio...";
          
          try {
            const base64Audio = await blobToBase64(audioBlob);
            const promptInput = document.getElementById("prompt-input");
            
            // Transcribe using Gemini API
            const transcription = await callGeminiAPI([
              {
                parts: [
                  { inlineData: { mimeType: "audio/mp3", data: base64Audio } },
                  { text: "Transcribe this audio recording exactly. Return ONLY the raw transcription text." }
                ]
              }
            ]);

            promptInput.value = (promptInput.value ? promptInput.value + " " : "") + transcription;
            alert("Voice transcribed successfully!");
          } catch (err) {
            alert("Audio transcription error: " + err.message);
          } finally {
            micBtn.innerHTML = "<span>🎤</span> Record Voice";
            state.isRecording = false;
          }
        };

        state.mediaRecorder.start();
        state.isRecording = true;
        micBtn.classList.add("recording");
        micBtn.innerHTML = "<span>🛑</span> Stop Recording";
      } catch (err) {
        alert("Microphone access error: " + err.message);
      }
    } else {
      if (state.mediaRecorder && state.mediaRecorder.state !== "inactive") {
        state.mediaRecorder.stop();
        state.mediaRecorder.stream.getTracks().forEach(track => track.stop());
      }
    }
  });
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result.split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

// ── Post Writer & Refinement ────────────────────────────────────────────────
async function initPostWriter() {
  const btnGen = document.getElementById("btn-generate");
  const btnClear = document.getElementById("btn-clear");
  const btnCreateJob = document.getElementById("btn-create-job");
  const btnCopyShare = document.getElementById("btn-copy-share");
  const previewBox = document.getElementById("post-preview");
  const promptInput = document.getElementById("prompt-input");
  const jobTitlePrompt = document.getElementById("job-title-prompt");

  if (!btnGen) return;

  let currentGeneratedJob = null;

  btnGen.addEventListener("click", async () => {
    const rawText = promptInput.value.trim();
    if (!rawText) {
      alert("Please enter or dictate a job description prompt first.");
      return;
    }

    btnGen.disabled = true;
    btnGen.innerHTML = "<span>⏳</span> Generating Post...";

    try {
      let jobTitle = rawText
        .replace(/generate a post for|create a post for|draft post for|we are hiring a|looking for a|hire a|create post|new job/gi, '')
        .replace(/at our company|he must be|she must be|with experience|for our team/gi, '')
        .trim();

      let words = jobTitle.split(/\s+/).slice(0, 4).join(" ");
      jobTitle = words || "Business Analyst";
      jobTitle = jobTitle.replace(/^["']|["']$/g, '');
      jobTitle = jobTitle.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');

      const companyName = state.companyName || 'Al Rahim Group';
      const contactEmail = state.contactEmail || 'danish.alrahimgroup@gmail.com';
      const memoryContext = `Company Name: ${companyName}\nCompany Intro: ${state.companyIntro || ''}\nApply Contact Email: ${contactEmail}`;

      const subjectTag = `ARG-${jobTitle.replace(/\s+/g, '-')}`;
      const applyLine = `\n\n👉 TO APPLY: Send your resume to ${contactEmail} with the subject line exactly containing '${subjectTag}'.`;

      let finalPostText = "";
      try {
        const generatedContent = await callGeminiAPI(
          [{ parts: [{ text: `Draft:\n${rawText}` }] }],
          `You are a professional LinkedIn content writer. Refine the rough draft into an engaging, professional LinkedIn job post for the position '${jobTitle}'. Use bullet points and emojis. Incorporate company context:\n${memoryContext}\nReturn ONLY the final post text.`
        );
        finalPostText = generatedContent + applyLine;
      } catch (e) {
        finalPostText = `🚀 WE ARE HIRING: ${jobTitle.toUpperCase()} at ${companyName}!\n\nWe are looking for a qualified ${jobTitle} to join our team.\n\nKey Details:\n• ${rawText}\n\n${applyLine}`;
      }

      previewBox.innerText = finalPostText;

      const job_id = `ARG-JD-${Date.now().toString().slice(-4)}`;
      currentGeneratedJob = {
        job_id,
        title: jobTitle,
        description: finalPostText,
        subject_tag: subjectTag,
        created_at: new Date().toISOString()
      };

      // Automatically save job to IndexedDB without extra button clicks or prompt popups!
      await addJob(currentGeneratedJob).catch(err => console.warn(err));
      workflowState.activeJob = currentGeneratedJob;
      workflowState.candidates = [];
      updateAgentContextUI();
      populateJobDropdowns().catch(err => console.warn(err));
      renderJobsList().catch(err => console.warn(err));

      if (btnCreateJob) btnCreateJob.disabled = false;
      if (btnCopyShare) btnCopyShare.disabled = false;
    } catch (err) {
      alert("Error generating post: " + err.message);
    } finally {
      btnGen.disabled = false;
      btnGen.innerHTML = "<span>✨</span> Generate Post";
    }
  });

// ── Global Job Creation Click Handler ─────────────────────────────────────────
window.createAndSaveJob = async function () {
  const previewBox = document.getElementById("post-preview");
  const promptInput = document.getElementById("prompt-input");

  let postText = previewBox ? previewBox.innerText.trim() : "";
  if (!postText || postText.includes("will appear here")) {
    postText = promptInput ? promptInput.value.trim() : "";
  }

  if (!postText) {
    alert("Please enter a job prompt or generate a post first.");
    return;
  }

  let jobTitle = postText
    .replace(/generate a post for|create a post for|draft post for|we are hiring a|looking for a|hire a|create post|new job/gi, '')
    .replace(/at our company|he must be|she must be|with experience|for our team/gi, '')
    .trim();

  let words = jobTitle.split(/\s+/).slice(0, 4).join(" ");
  jobTitle = words || "Business Analyst";
  jobTitle = jobTitle.replace(/^["']|["']$/g, '');
  jobTitle = jobTitle.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');

  const companyName = state.companyName || 'Al Rahim Group';
  const contactEmail = state.contactEmail || 'danish.alrahimgroup@gmail.com';
  const subjectTag = `ARG-${jobTitle.replace(/\s+/g, '-')}`;

  const job_id = `ARG-JD-${Date.now().toString().slice(-4)}`;
  const newJob = {
    job_id,
    title: jobTitle,
    description: postText,
    subject_tag: subjectTag,
    created_at: new Date().toISOString()
  };

  try {
    await addJob(newJob);
    workflowState.activeJob = newJob;
    workflowState.candidates = [];
    updateAgentContextUI();
    await populateJobDropdowns();
    await renderJobsList();
    alert(`Job Position '${jobTitle}' (ID: ${job_id}) saved successfully to device memory!`);
  } catch (err) {
    alert("Error saving job position: " + err.message);
  }
};

  btnClear.addEventListener("click", () => {
    promptInput.value = "";
    if (jobTitlePrompt) jobTitlePrompt.value = "";
    previewBox.innerText = "Your generated LinkedIn post draft will appear here...";
    if (btnCreateJob) btnCreateJob.disabled = true;
    if (btnCopyShare) btnCopyShare.disabled = true;
    currentGeneratedJob = null;
  });

  btnCopyShare.addEventListener("click", async () => {
    const textToCopy = previewBox.innerText;
    if (!textToCopy || textToCopy.includes("will appear here")) return;

    try {
      await navigator.clipboard.writeText(textToCopy);
      
      if (navigator.share) {
        await navigator.share({ title: "LinkedIn Job Posting", text: textToCopy });
      } else {
        alert("Job post copied to clipboard! Open LinkedIn app to publish.");
        window.open("https://www.linkedin.com/", "_blank");
      }
    } catch (err) {
      alert("Copied to clipboard!");
    }
  });
}



// ── PDF Text Parser with pdf.js & Gemini OCR Fallback ────────────────────────
async function extractTextFromPDF(file) {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = async (e) => {
      try {
        const typedArray = new Uint8Array(e.target.result);
        const pdf = await window.pdfjsLib.getDocument(typedArray).promise;
        let fullText = "";

        for (let i = 1; i <= pdf.numPages; i++) {
          const page = await pdf.getPage(i);
          const textContent = await page.getTextContent();
          const pageText = textContent.items.map(item => item.str).join(" ");
          fullText += pageText + "\n";
        }

        fullText = fullText.trim();
        const wordCount = fullText.split(/\s+/).filter(Boolean).length;

        if (wordCount < 50) {
          console.log("PDF text word count low (" + wordCount + "). Triggering Gemini OCR fallback...");
          const base64Pdf = arrayBufferToBase64(e.target.result);
          const ocrText = await callGeminiAPI([
            {
              parts: [
                { inlineData: { mimeType: "application/pdf", data: base64Pdf } },
                { text: "Extract ALL text content from this scanned resume PDF. Return ONLY the raw extracted text." }
              ]
            }
          ]).catch(() => "");
          if (ocrText) fullText = ocrText;
        }

        resolve(fullText || "[Scanned/Image Resume File]");
      } catch (err) {
        console.warn("PDF parse error:", err);
        resolve("[Scanned/Image Resume File]");
      }
    };
    reader.readAsArrayBuffer(file);
  });
}

function arrayBufferToBase64(buffer) {
  let binary = '';
  const bytes = new Uint8Array(buffer);
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return window.btoa(binary);
}

// ── Candidate Scoring Workflow (Multi-Dimensional) ───────────────────────────
async function initCandidateEvaluator() {
  const fileInput = document.getElementById("resume-file-input");
  const jobSelect = document.getElementById("eval-job-select");
  const candSelect = document.getElementById("eval-cand-select");
  const btnScore = document.getElementById("btn-score-candidates");

  if (!jobSelect) return;

  jobSelect.addEventListener("change", async () => {
    state.selectedJobId = jobSelect.value;
    btnScore.disabled = !state.selectedJobId;
    await populateCandidateDropdown();
    await renderCandidatesList();
  });

  if (candSelect) {
    candSelect.addEventListener("change", async () => {
      await renderCandidatesList();
    });
  }

  fileInput.addEventListener("change", async (e) => {
    const files = Array.from(e.target.files);
    if (files.length === 0) return;

    const allJobs = await getAllJobs();

    for (const file of files) {
      let parsedText = "";
      if (file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")) {
        parsedText = await extractTextFromPDF(file);
      } else {
        parsedText = await file.text().catch(() => "[File content]");
      }

      const txtFilename = file.name.replace(/\.[^/.]+$/, "") + ".txt";

      // Auto-match target job_id using subject_tag if present in file text/name, fallback to state.selectedJobId
      let targetJobId = state.selectedJobId;
      if (allJobs.length > 0) {
        for (const j of allJobs) {
          const tagClean = (j.subject_tag || "").toLowerCase();
          const titleClean = (j.title || "").toLowerCase();
          const fileClean = (file.name + " " + parsedText.slice(0, 500)).toLowerCase();
          
          if (tagClean && fileClean.includes(tagClean)) {
            targetJobId = j.job_id;
            break;
          } else if (titleClean && fileClean.includes(titleClean)) {
            targetJobId = j.job_id;
            break;
          }
        }
      }

      if (!targetJobId && allJobs.length > 0) {
        targetJobId = allJobs[0].job_id;
      }

      if (!targetJobId) {
        alert("Please create a Job Position in Tab 1 or Tab 2 first.");
        fileInput.value = "";
        return;
      }

      await addCandidate({
        job_id: targetJobId,
        name: file.name.replace(/\.[^/.]+$/, ""),
        email: state.contactEmail || "candidate@email.com",
        resume_name: file.name,
        txt_file: txtFilename,
        parsed_text: parsedText,
        relevance_score: null,
        status: "Applied",
        applied_at: new Date().toISOString()
      });
    }

    fileInput.value = "";
    if (state.selectedJobId) {
      await populateCandidateDropdown();
      await renderCandidatesList();
    }
    await renderJobsList();
    alert(`Uploaded & matched ${files.length} candidate resume(s)!`);
  });

  btnScore.addEventListener("click", async () => {
    if (!state.selectedJobId) return;

    btnScore.disabled = true;
    btnScore.innerHTML = "<span>🤖</span> Scoring Candidates with Gemini AI...";

    try {
      const jobs = await getAllJobs();
      const job = jobs.find(j => j.job_id === state.selectedJobId);
      if (!job) return;

      const candidates = await getCandidatesByJob(state.selectedJobId);
      const unscored = candidates.filter(c => c.status === "Applied");

      if (unscored.length === 0) {
        alert("No unscored candidates for this job position.");
        return;
      }

      for (const cand of unscored) {
        const prompt = `Perform a multi-dimensional analysis of candidate resume vs job requirement.
Job Title: ${job.title}
Job Description:
${job.description}

Candidate Resume Text:
${cand.parsed_text}

Evaluate across:
1. Skills Match (0-35)
2. Experience Match (0-35)
3. Education (0-15)
4. Location & Fit (0-15)

Calculate Total Score = sum of above (0-100).
Assign Recommendation: "HIRE" (score >= 80), "INTERVIEW" (score 55-79), "REJECT" (score < 55).

Return STRICT JSON ONLY:
{
  "skills_score": 30,
  "experience_score": 28,
  "education_score": 12,
  "location_score": 14,
  "score": 84,
  "recommendation": "INTERVIEW",
  "match_summary": "2 sentence executive summary",
  "strengths": ["strength 1", "strength 2"],
  "gaps": ["gap 1"]
}`;

        try {
          const rawResult = await callGeminiAPI([{ parts: [{ text: prompt }] }]);
          const cleanJsonStr = rawResult.replace(/```json/g, "").replace(/```/g, "").trim();
          const evalJson = JSON.parse(cleanJsonStr);

          cand.skills_score = evalJson.skills_score || 0;
          cand.experience_score = evalJson.experience_score || 0;
          cand.education_score = evalJson.education_score || 0;
          cand.location_score = evalJson.location_score || 0;
          cand.relevance_score = evalJson.score || evalJson.relevance_score || 0;
          cand.recommendation = evalJson.recommendation || "INTERVIEW";
          cand.summary = evalJson.match_summary || evalJson.summary || "";
          cand.strengths = evalJson.strengths || [];
          cand.gaps = evalJson.gaps || [];
          cand.status = "Scored";

          await updateCandidate(cand);
        } catch (evalErr) {
          console.error("Candidate evaluation error:", evalErr);
        }
      }

      await populateCandidateDropdown();
      await renderCandidatesList();
      await renderJobsList();
      alert("Successfully evaluated candidates!");
    } catch (err) {
      alert("Error scoring candidates: " + err.message);
    } finally {
      btnScore.disabled = false;
      btnScore.innerHTML = "<span>🤖</span> Score Unscored Candidates with Gemini";
    }
  });
}

// ── PDF Viewer & Interview Scheduling Modal Global Handlers ─────────────────
let cachedCandidates = [];

window.viewCandidatePdf = async function (candId) {
  const modal = document.getElementById("pdf-modal");
  const container = document.getElementById("pdf-viewer-container");
  const title = document.getElementById("pdf-modal-title");
  if (!modal || !container) return;

  const db = await import('./db.js');
  const allJobs = await db.getAllJobs();
  let candidate = null;

  for (const j of allJobs) {
    const candidates = await db.getCandidatesByJob(j.job_id);
    const found = candidates.find(c => String(c.candidate_id) === String(candId));
    if (found) {
      candidate = found;
      break;
    }
  }

  if (!candidate) {
    alert("Candidate details not found.");
    return;
  }

  const pdfFileName = candidate.resume_name || `${candidate.name}.pdf`;
  const pdfApiUrl = `${getApiBaseUrl()}/api/candidate-pdf/${encodeURIComponent(candidate.candidate_id || pdfFileName)}`;

  if (title) {
    title.innerHTML = `📄 Candidate Resume PDF: <strong>${pdfFileName}</strong> 
      <a href="${pdfApiUrl}" target="_blank" style="margin-left: 12px; font-size: 12px; color: #34d399; text-decoration: underline;">Open PDF in New Window ↗</a>`;
  }

  // 1. If stored as File/Blob object in IndexedDB
  if (candidate.pdf_blob) {
    try {
      const blobUrl = URL.createObjectURL(candidate.pdf_blob);
      container.innerHTML = `<iframe src="${blobUrl}" style="width: 100%; height: 100%; border: none;"></iframe>`;
      modal.style.display = "flex";
      return;
    } catch (e) {}
  }

  // 2. Fetch PDF file bytes directly from local backend API and render via Blob URL
  try {
    const res = await fetch(pdfApiUrl).catch(() => null);
    if (res && res.ok) {
      const pdfBlob = await res.blob();
      const blobUrl = URL.createObjectURL(pdfBlob);
      container.innerHTML = `<iframe src="${blobUrl}" style="width: 100%; height: 100%; border: none;"></iframe>`;
      modal.style.display = "flex";
      return;
    }
  } catch (e) {
    console.error("Failed to fetch PDF bytes from backend:", e);
  }

  // 3. Fallback: Render parsed text content inside viewer
  container.innerHTML = `
    <div style="padding: 24px; color: #f8fafc; height: 100%; overflow-y: auto; background: #0f172a;">
      <h2 style="color: #60a5fa; margin-bottom: 4px;">👤 Candidate: ${candidate.name}</h2>
      <div style="color: #94a3b8; font-size: 13px; margin-bottom: 16px; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 10px;">
        Email: ${candidate.email || 'N/A'} | Status: ${candidate.status || 'Applied'} | File: ${pdfFileName}
      </div>
      <h3>📄 Parsed Resume Text Content (.txt):</h3>
      <pre style="white-space: pre-wrap; word-wrap: break-word; background: #1e293b; padding: 20px; border-radius: 8px; font-size: 14px; color: #e2e8f0; border: 1px solid rgba(255,255,255,0.1);">${(candidate.parsed_text || "No text content extracted.").replace(/</g, "&lt;").replace(/>/g, "&gt;")}</pre>
    </div>
  `;
  modal.style.display = "flex";
};

window.closePdfModal = function () {
  const modal = document.getElementById("pdf-modal");
  if (modal) modal.style.display = "none";
};

window.openInterviewModal = async function (candId) {
  const modal = document.getElementById("interview-modal");
  const candIdInput = document.getElementById("interview-cand-id");
  const candNameInput = document.getElementById("interview-cand-name");
  const candEmailInput = document.getElementById("interview-cand-email");
  const dateInput = document.getElementById("interview-date");
  const dayInput = document.getElementById("interview-day");
  if (!modal) return;

  const db = await import('./db.js');
  const allJobs = await db.getAllJobs();
  let candidate = null;
  let jobTitle = "Position";

  for (const j of allJobs) {
    const candidates = await db.getCandidatesByJob(j.job_id);
    const found = candidates.find(c => String(c.candidate_id) === String(candId));
    if (found) {
      candidate = found;
      jobTitle = j.title;
      break;
    }
  }

  if (!candidate) {
    alert("Candidate details not found.");
    return;
  }

  // Clean candidate name (strip file extensions and words like Resume/CV)
  let cleanName = candidate.name || "";
  cleanName = cleanName.replace(/\.[^/.]+$/, "").replace(/_|-/g, " ");
  cleanName = cleanName.replace(/\b(resume|cv|academic|portfolio|application)\b/gi, "");
  cleanName = cleanName.trim() || candidate.name;

  if (candIdInput) candIdInput.value = candidate.candidate_id;
  if (candNameInput) candNameInput.value = cleanName;
  if (candEmailInput) candEmailInput.value = (candidate.email && candidate.email !== state.contactEmail) ? candidate.email : "";

  // Set default interview date (tomorrow)
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  if (dateInput) dateInput.value = tomorrow.toISOString().split("T")[0];

  const days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  if (dayInput) dayInput.value = days[tomorrow.getDay()];

  modal.style.display = "flex";
};

window.closeInterviewModal = function () {
  const modal = document.getElementById("interview-modal");
  if (modal) modal.style.display = "none";
};

window.sendInterviewEmail = async function () {
  const candId = document.getElementById("interview-cand-id")?.value;
  const candName = document.getElementById("interview-cand-name")?.value?.trim();
  const candEmail = document.getElementById("interview-cand-email")?.value?.trim();
  const date = document.getElementById("interview-date")?.value;
  const day = document.getElementById("interview-day")?.value;
  const time = document.getElementById("interview-time")?.value;
  const format = document.getElementById("interview-type")?.value;
  const location = document.getElementById("interview-location")?.value || "Head Office / Online";
  const notes = document.getElementById("interview-notes")?.value || "";
  const btnSend = document.getElementById("btn-send-interview");

  if (!candName) {
    alert("Please enter the Candidate's Name.");
    return;
  }

  if (!candEmail || !candEmail.includes("@")) {
    alert("Please enter a valid Candidate Email address.");
    return;
  }

  if (!date || !time) {
    alert("Please select an interview Date and Time.");
    return;
  }

  const db = await import('./db.js');
  const allJobs = await db.getAllJobs();
  let candidate = null;
  let jobTitle = "Position";

  for (const j of allJobs) {
    const candidates = await db.getCandidatesByJob(j.job_id);
    const found = candidates.find(c => String(c.candidate_id) === String(candId));
    if (found) {
      candidate = found;
      jobTitle = j.title;
      break;
    }
  }

  if (!candidate) return;

  if (btnSend) {
    btnSend.disabled = true;
    btnSend.innerHTML = "<span>⏳</span> Dispatching Email via SMTP...";
  }

  try {
    const payload = {
      candidate_name: candName,
      candidate_email: candEmail,
      job_title: jobTitle,
      interview_date: date,
      interview_day: day,
      interview_time: time,
      interview_type: format,
      interview_location: location,
      notes: notes
    };

    const response = await fetch(`${getApiBaseUrl()}/api/send-interview-email`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const resultData = await response.json().catch(() => ({}));

    if (response.ok) {
      candidate.name = candName;
      candidate.email = candEmail;
      candidate.status = "Interview Scheduled";
      await db.updateCandidate(candidate);
      window.closeInterviewModal();
      await renderCandidatesList();
      await renderJobsList();
      alert(`✉️ Call for Interview email successfully sent in background to:\n${candName} <${candEmail}>`);
    } else {
      alert(`Error sending email: ${resultData.detail || 'Failed to dispatch via Gmail SMTP.'}`);
    }
  } catch (err) {
    alert("Error connecting to email service: " + err.message);
  } finally {
    if (btnSend) {
      btnSend.disabled = false;
      btnSend.innerHTML = "<span>✉️</span> Send Interview Call Email";
    }
  }
};


async function populateCandidateDropdown() {
  const select = document.getElementById("eval-cand-select");
  if (!select) return;

  if (!state.selectedJobId) {
    select.innerHTML = '<option value="">-- All Candidates for Selected Job --</option>';
    select.disabled = true;
    return;
  }

  const candidates = await getCandidatesByJob(state.selectedJobId);
  select.disabled = false;

  let options = '<option value="ALL">-- All Candidates for Selected Job (' + candidates.length + ') --</option>';
  options += candidates.map(c => {
    const scoreText = c.relevance_score !== null ? `${c.relevance_score}% [${c.recommendation}]` : 'Applied';
    const resumeLabel = c.resume_name || `${c.name}.pdf`;
    return `<option value="${c.candidate_id}">${c.name} - ${resumeLabel} (${scoreText})</option>`;
  }).join('');

  select.innerHTML = options;
}

async function renderCandidatesList() {
  const container = document.getElementById("candidates-cards-container");
  const candSelect = document.getElementById("eval-cand-select");
  if (!container) return;

  if (!state.selectedJobId) {
    container.innerHTML = '<p style="color: var(--text-muted); font-size: 14px;">Select a job position above to view candidate evaluations.</p>';
    return;
  }

  let candidates = await getCandidatesByJob(state.selectedJobId);
  if (candidates.length === 0) {
    container.innerHTML = '<p style="color: var(--text-muted); font-size: 14px;">No candidates uploaded for this job position yet.</p>';
    return;
  }

  const selectedCandId = candSelect ? candSelect.value : "ALL";
  if (selectedCandId && selectedCandId !== "ALL") {
    candidates = candidates.filter(c => String(c.candidate_id) === String(selectedCandId));
  }

  container.innerHTML = candidates.map(c => {
    const recClass = c.recommendation ? `badge-${c.recommendation}` : 'badge-INTERVIEW';
    const scoreVal = c.relevance_score !== null ? `${c.relevance_score}%` : 'Unscored';
    
    const strengthsHtml = Array.isArray(c.strengths) && c.strengths.length > 0
      ? c.strengths.map(s => `• ${s}`).join('<br>') : 'N/A';
    const gapsHtml = Array.isArray(c.gaps) && c.gaps.length > 0
      ? c.gaps.map(g => `• ${g}`).join('<br>') : 'N/A';

    const pdfName = c.resume_name || `${c.name}.pdf`;
    const txtName = c.txt_file || (c.resume_name ? c.resume_name.replace(/\.[^/.]+$/, "") + ".txt" : `${c.name}.txt`);

    return `
      <div class="candidate-card">
        <div class="cand-header">
          <span class="cand-name">👤 ${c.name} (${scoreVal})</span>
          ${c.recommendation ? `<span class="badge-rec ${recClass}">${c.recommendation}</span>` : ''}
        </div>
        
        <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
          <span>📁 Files: <code>${pdfName}</code> & <code>${txtName}</code></span>
          <div class="btn-group">
            <button onclick="window.viewCandidatePdf(${c.candidate_id})" class="btn btn-secondary" style="font-size: 11px; padding: 4px 10px;">👁️ View PDF</button>
            <button onclick="window.openInterviewModal(${c.candidate_id})" class="btn btn-accent" style="font-size: 11px; padding: 4px 10px;">📅 Call for Interview</button>
          </div>
        </div>

        ${c.relevance_score !== null ? `
          <div class="score-bar-group">
            <div class="score-bar-label">
              <span>Overall Suitability Score</span>
              <span>${c.relevance_score}/100</span>
            </div>
            <div class="progress-track">
              <div class="progress-fill" style="width: ${c.relevance_score}%;"></div>
            </div>
          </div>

          <div style="font-size: 12px; color: var(--text-muted); display: flex; justify-content: space-between; margin-top: 6px;">
            <span>Skills: ${c.skills_score || 0}/35</span>
            <span>Exp: ${c.experience_score || 0}/35</span>
            <span>Edu: ${c.education_score || 0}/15</span>
            <span>Loc: ${c.location_score || 0}/15</span>
          </div>
        ` : ''}

        <div class="cand-summary"><strong>Executive Summary:</strong> ${c.summary || 'Applied'}</div>

        ${c.status === "Scored" || c.status === "Interview Scheduled" ? `
          <div class="strengths-gaps">
            <div class="sg-box">
              <div class="sg-title strength">Key Strengths</div>
              <div>${strengthsHtml}</div>
            </div>
            <div class="sg-box">
              <div class="sg-title gap">Gaps / Missing</div>
              <div>${gapsHtml}</div>
            </div>
          </div>
        ` : ''}
      </div>
    `;
  }).join('');
}

// ── Reusable Fetch & Auto-Score Pipeline (Used by Manual Button & Cron Job) ─
async function triggerFetchAndAutoScore(silent = false) {
  const syncStatusMsg = document.getElementById("sync-status-msg");
  const cronLogMsg = document.getElementById("cron-log-msg");

  if (!silent && syncStatusMsg) {
    syncStatusMsg.innerText = "Connecting to Gmail, downloading resumes, and running multi-dimensional AI scoring in one go...";
  }

  try {
    const localJobs = await getAllJobs();
    for (const j of localJobs) {
      await fetch(`${getApiBaseUrl()}/api/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(j)
      }).catch(() => null);
    }

    const response = await fetch(`${getApiBaseUrl()}/api/sync-resumes`, { method: "POST" }).catch(() => null);
    if (response && response.ok) {
      const data = await response.json();
      const syncCount = data.synced_count || 0;
      const scoredCount = data.scored_count || 0;

      for (const j of localJobs) {
        const candRes = await fetch(`${getApiBaseUrl()}/api/candidates/${j.job_id}`).catch(() => null);
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

      await renderJobsList();
      await populateJobDropdowns();
      await renderCandidatesList();

      const timeStr = new Date().toLocaleTimeString();
      const statusText = `✅ Cron Check ${timeStr}: Fetched ${syncCount} resume(s), Scored ${scoredCount} candidate(s).`;
      if (syncStatusMsg) syncStatusMsg.innerText = statusText;
      if (cronLogMsg) cronLogMsg.innerText = `⏱️ Background Cron Job: ${statusText}`;

      return { syncCount, scoredCount };
    }
  } catch (err) {
    if (cronLogMsg) cronLogMsg.innerText = `⏱️ Cron Check Notice: Backend server offline.`;
  }
  return { syncCount: 0, scoredCount: 0 };
}

// ── Background Cron Job Scheduler (Live Timer Beside Upload Button) ──────────
let cronTimerId = null;
let cronCountdownId = null;
let cronIsEnabled = false;
let remainingSeconds = 0;

function initCronScheduler() {
  const btnToggle = document.getElementById("btn-cron-toggle");
  const intervalSelect = document.getElementById("cron-interval-select");
  const iconSpan = document.getElementById("cron-toggle-icon");
  const textSpan = document.getElementById("cron-toggle-text");
  const badgeSpan = document.getElementById("cron-countdown-badge");
  const cronLogMsg = document.getElementById("cron-log-msg");

  if (!btnToggle || !intervalSelect) return;

  function formatTime(totalSec) {
    const m = Math.floor(totalSec / 60).toString().padStart(2, '0');
    const s = (totalSec % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
  }

  function stopCron() {
    if (cronTimerId) {
      clearInterval(cronTimerId);
      cronTimerId = null;
    }
    if (cronCountdownId) {
      clearInterval(cronCountdownId);
      cronCountdownId = null;
    }
    cronIsEnabled = false;
    if (iconSpan) iconSpan.innerText = "▶";
    if (textSpan) textSpan.innerText = "Start Auto-Sync";
    if (badgeSpan) badgeSpan.style.display = "none";
    if (btnToggle) {
      btnToggle.className = "btn btn-secondary";
    }
    if (cronLogMsg) cronLogMsg.innerText = "⏱️ Auto-Sync Cron Status: Off (Click 'Start Auto-Sync' to check Gmail automatically).";
  }

  function startCron() {
    stopCron();
    cronIsEnabled = true;
    const intervalMins = parseInt(intervalSelect.value, 10) || 5;
    const totalSec = intervalMins * 60;
    remainingSeconds = totalSec;

    if (iconSpan) iconSpan.innerText = "⏹";
    if (textSpan) textSpan.innerText = "Stop Auto-Sync";
    if (badgeSpan) {
      badgeSpan.style.display = "inline-block";
      badgeSpan.innerText = formatTime(remainingSeconds);
    }
    if (btnToggle) {
      btnToggle.className = "btn btn-accent";
    }

    if (cronLogMsg) cronLogMsg.innerText = `⏱️ Background Auto-Sync ACTIVE: Automatically checking Gmail every ${intervalMins} minute(s)...`;

    // Trigger initial immediate run
    triggerFetchAndAutoScore(true);

    // Ticking countdown timer
    cronCountdownId = setInterval(() => {
      remainingSeconds--;
      if (remainingSeconds <= 0) {
        remainingSeconds = totalSec;
        triggerFetchAndAutoScore(true);
      }
      if (badgeSpan) badgeSpan.innerText = formatTime(remainingSeconds);
    }, 1000);
  }

  btnToggle.addEventListener("click", () => {
    if (cronIsEnabled) {
      stopCron();
    } else {
      startCron();
    }
  });

  intervalSelect.addEventListener("change", () => {
    if (cronIsEnabled) {
      startCron();
    }
  });
}

// ── Jobs & Email Resumes Management ─────────────────────────────────────────
async function initJobsManager() {
  const btnSyncEmails = document.getElementById("btn-sync-emails");
  const tab2ResumeInput = document.getElementById("tab2-resume-input");
  const syncStatusMsg = document.getElementById("sync-status-msg");

  initCronScheduler();

  if (btnSyncEmails) {
    btnSyncEmails.addEventListener("click", async () => {
      btnSyncEmails.disabled = true;
      btnSyncEmails.innerHTML = "<span>⏳</span> Fetching Emails & Running AI Scoring...";
      try {
        const { syncCount, scoredCount } = await triggerFetchAndAutoScore(false);
        alert(`🎉 All-in-One Fetch & Auto-Scoring Complete!\n\n• Resumes Fetched from Gmail: ${syncCount}\n• Candidates Evaluated with Gemini AI: ${scoredCount}`);
      } finally {
        btnSyncEmails.disabled = false;
        btnSyncEmails.innerHTML = "<span>🔄</span> Fetch Email Resumes (Gmail Sync)";
      }
    });
  }

  if (tab2ResumeInput) {
    tab2ResumeInput.addEventListener("change", async (e) => {
      const files = Array.from(e.target.files);
      if (files.length === 0) return;

      const allJobs = await getAllJobs();
      let addedCount = 0;

      for (const file of files) {
        let parsedText = "";
        if (file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")) {
          parsedText = await extractTextFromPDF(file);
        } else {
          parsedText = await file.text().catch(() => "[Text file content]");
        }

        const txtFilename = file.name.replace(/\.[^/.]+$/, "") + ".txt";

        // Auto-match target job position by subject_tag or title
        let targetJob = null;
        if (allJobs.length > 0) {
          for (const j of allJobs) {
            const tagClean = (j.subject_tag || "").toLowerCase();
            const titleClean = (j.title || "").toLowerCase();
            const fileClean = (file.name + " " + parsedText.slice(0, 500)).toLowerCase();

            if (tagClean && fileClean.includes(tagClean)) {
              targetJob = j;
              break;
            } else if (titleClean && fileClean.includes(titleClean)) {
              targetJob = j;
              break;
            }
          }
          if (!targetJob) targetJob = allJobs[0];
        }

        if (targetJob) {
          // Automatic Gemini AI Multi-Dimensional Scoring in place!
          let scoreRes = null;
          try {
            const scorePrompt = `System: You are an expert HR recruiter for ${state.companyName || 'the company'}. Evaluate the following resume against the job description across 4 dimensions:
1. Skills Match (0-35 points)
2. Experience Level (0-35 points)
3. Education & Credentials (0-15 points)
4. Location / Fit (0-15 points)

Job Title: ${targetJob.title}
Job Description: ${targetJob.description}

Resume Content:
${parsedText.slice(0, 4000)}

Respond strictly with valid JSON format:
{
  "skills_score": 30,
  "experience_score": 28,
  "education_score": 12,
  "location_score": 14,
  "score": 84,
  "recommendation": "HIRE",
  "strengths": ["Strong Python experience", "AI prompt engineering"],
  "gaps": ["No direct Kubernetes experience"],
  "match_summary": "Excellent fit with solid technical and domain experience."
}`;
            const geminiRaw = await callGeminiAPI(scorePrompt);
            const jsonText = geminiRaw.replace(/```json/g, "").replace(/```/g, "").trim();
            scoreRes = JSON.parse(jsonText);
          } catch (e) {
            console.error("Auto-scoring error during upload:", e);
          }

          const relevanceScore = scoreRes ? (scoreRes.score || 70) : null;

          await addCandidate({
            job_id: targetJob.job_id,
            name: file.name.replace(/\.[^/.]+$/, ""),
            email: state.contactEmail || "applicant@email.com",
            resume_name: file.name,
            txt_file: txtFilename,
            parsed_text: parsedText,
            pdf_blob: file, // Store raw PDF File blob for instant native PDF viewing
            relevance_score: relevanceScore,
            skills_score: scoreRes?.skills_score || 0,
            experience_score: scoreRes?.experience_score || 0,
            education_score: scoreRes?.education_score || 0,
            location_score: scoreRes?.location_score || 0,
            recommendation: scoreRes?.recommendation || (relevanceScore >= 80 ? "HIRE" : relevanceScore >= 55 ? "INTERVIEW" : "REJECT"),
            strengths: scoreRes?.strengths || ["Extracted from uploaded resume"],
            gaps: scoreRes?.gaps || [],
            summary: scoreRes?.match_summary || "Uploaded and evaluated automatically.",
            status: scoreRes ? "Scored" : "Applied",
            applied_at: new Date().toISOString()
          });
          addedCount++;
        }
      }

      tab2ResumeInput.value = "";
      if (syncStatusMsg) syncStatusMsg.innerText = `✅ Processed, extracted text, and automatically evaluated AI scores for ${addedCount} resume PDF file(s) in one go!`;
      await renderJobsList();
      await populateJobDropdowns();
      await renderCandidatesList();
      alert(`🎉 Successfully uploaded, extracted text, and evaluated AI scores for ${addedCount} candidate resume(s) in one go!`);
    });
  }

  await renderJobsList();
  await populateJobDropdowns();
}


async function renderJobsList() {
  const container = document.getElementById("jobs-list-container");
  if (!container) return;

  const jobs = await getAllJobs();
  if (jobs.length === 0) {
    container.innerHTML = '<p style="color: var(--text-muted); font-size: 14px;">No active job positions tracked in IndexedDB yet. Generate a post in Tab 1 and click \'Create & Save Job Position\'.</p>';
    return;
  }

  const jobsWithResumes = await Promise.all(jobs.map(async (j) => {
    const candidates = await getCandidatesByJob(j.job_id);
    return { job: j, candidates };
  }));

  container.innerHTML = jobsWithResumes.map(({ job, candidates }) => {
    const resumesListHtml = candidates.length > 0 ? candidates.map(c => {
      const pdfName = c.resume_name || `${c.name}.pdf`;
      const txtName = c.txt_file || (c.resume_name ? c.resume_name.replace(/\.[^/.]+$/, "") + ".txt" : `${c.name}.txt`);
      const scoreBadge = c.relevance_score !== null ? `<span class="badge-rec badge-${c.recommendation}">${c.relevance_score}% ${c.recommendation}</span>` : '<span class="status-badge" style="background: rgba(255,255,255,0.1); color: #94a3b8;">Applied</span>';

      return `
        <div style="background: rgba(15,23,42,0.7); padding: 10px 14px; border-radius: 8px; margin-top: 8px; display: flex; justify-content: space-between; align-items: center; gap: 10px; font-size: 13px; border: 1px solid rgba(255,255,255,0.08);">
          <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
            <strong style="color: #f8fafc; font-size: 14px;">👤 ${c.name}</strong>
            <button onclick="window.openInterviewModal(${c.candidate_id})" class="btn btn-accent" style="font-size: 11px; padding: 4px 10px; line-height: 1;">📅 Call for Interview</button>
            <button onclick="window.viewCandidatePdf(${c.candidate_id})" class="btn btn-secondary" style="font-size: 11px; padding: 4px 10px; line-height: 1; background: rgba(59,130,246,0.2); color: #60a5fa; border: 1px solid rgba(96,165,250,0.35);">📄 Open ${pdfName}</button>
          </div>
          <div>${scoreBadge}</div>
        </div>
      `;
    }).join('') : '<p style="font-size: 12px; color: var(--text-muted); margin-top: 6px;">No applicant resumes received under this job yet.</p>';

    return `
      <div class="candidate-card" style="margin-bottom: 16px;">
        <div class="cand-header">
          <span class="cand-name">💼 ${job.title}</span>
          <span class="status-badge">${job.job_id}</span>
        </div>
        <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 8px;">Tag: <code>${job.subject_tag}</code></p>
        <div style="font-size: 13px; color: #cbd5e1; white-space: pre-wrap; background: rgba(15,23,42,0.5); padding: 12px; border-radius: 8px; max-height: 220px; overflow-y: auto; border: 1px solid rgba(255,255,255,0.06); margin-bottom: 12px;">${job.description}</div>

        <div style="margin-top: 12px; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 10px;">
          <strong style="font-size: 13px; color: #60a5fa;">📥 Resumes Received under this Job (${candidates.length}):</strong>
          <div style="margin-top: 6px;">${resumesListHtml}</div>
        </div>

        <button class="btn btn-danger btn-delete-job" data-id="${job.job_id}" style="margin-top: 12px; font-size: 12px; padding: 6px 12px;">Delete Job</button>
      </div>
    `;
  }).join('');

  container.querySelectorAll(".btn-delete-job").forEach(btn => {
    btn.addEventListener("click", async (e) => {
      const id = e.target.getAttribute("data-id");
      if (confirm("Delete this job position?")) {
        await deleteJob(id);
        await renderJobsList();
        await populateJobDropdowns();
      }
    });
  });
}

async function populateJobDropdowns() {
  const select = document.getElementById("eval-job-select");
  if (!select) return;

  const jobs = await getAllJobs();
  select.innerHTML = '<option value="">-- Choose Job Position --</option>' +
    jobs.map(j => `<option value="${j.job_id}">${j.job_id} - ${j.title}</option>`).join('');
}

window.refreshJobsUI = async function() {
  try {
    await renderJobsList();
    await populateJobDropdowns();
  } catch (e) {
    console.warn("refreshJobsUI error:", e);
  }
};

// ── Settings Management ──────────────────────────────────────────────────────
window.saveAppSettings = async function(e) {
  if (e && e.preventDefault) e.preventDefault();
  const keyInput = document.getElementById("setting-gemini-key");
  const nameInput = document.getElementById("setting-company-name");
  const introInput = document.getElementById("setting-company-intro");
  const emailInput = document.getElementById("setting-contact-email");

  const valKey = keyInput ? keyInput.value.trim() : "";
  const valName = nameInput ? nameInput.value.trim() : "Al Rahim Group";
  const valIntro = introInput ? introInput.value.trim() : "";
  const valEmail = emailInput ? emailInput.value.trim() : "danish.alrahimgroup@gmail.com";

  state.geminiKey = valKey;
  state.companyName = valName;
  state.companyIntro = valIntro;
  state.contactEmail = valEmail;

  await setSetting("GEMINI_API_KEY", valKey);
  await setSetting("COMPANY_NAME", valName);
  await setSetting("COMPANY_INTRO", valIntro);
  await setSetting("CONTACT_EMAIL", valEmail);

  alert("✅ Settings saved securely to local IndexedDB!");
};

async function initSettings() {
  const btnSave = document.getElementById("btn-save-settings");
  const keyInput = document.getElementById("setting-gemini-key");
  const nameInput = document.getElementById("setting-company-name");
  const introInput = document.getElementById("setting-company-intro");
  const emailInput = document.getElementById("setting-contact-email");

  // Load existing settings from IndexedDB; fallback to initial .env defaults
  state.geminiKey = await getSetting("GEMINI_API_KEY", "");
  state.companyName = await getSetting("COMPANY_NAME", "Al Rahim Group");
  state.companyIntro = await getSetting("COMPANY_INTRO", "A leading business conglomerate specializing in global trade, engineering, and manufacturing.");
  state.contactEmail = await getSetting("CONTACT_EMAIL", "danish.alrahimgroup@gmail.com");

  // Populate input fields with saved or default initial values
  if (keyInput) keyInput.value = state.geminiKey;
  if (nameInput) nameInput.value = state.companyName;
  if (introInput) introInput.value = state.companyIntro;
  if (emailInput) emailInput.value = state.contactEmail;

  if (btnSave) {
    btnSave.addEventListener("click", window.saveAppSettings);
  }
}

// Voice agent logic lives in voice_agent.js (loaded as ES module from index.html)

function initCloudSyncUI() {
  const btnExport = document.getElementById("btn-export-db");
  const inputImport = document.getElementById("btn-import-db-input");
  const btnPush = document.getElementById("btn-sync-cloud-push");
  const btnPull = document.getElementById("btn-sync-cloud-pull");
  const endpointInput = document.getElementById("setting-cloud-endpoint");
  const keyInput = document.getElementById("setting-cloud-key");
  const msgDiv = document.getElementById("cloud-sync-msg");

  if (btnExport) {
    btnExport.addEventListener("click", async () => {
      try {
        const json = await exportDatabaseToJSON();
        const blob = new Blob([JSON.stringify(json, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `recruiter_db_backup_${new Date().toISOString().slice(0, 10)}.json`;
        a.click();
        URL.revokeObjectURL(url);
        if (msgDiv) msgDiv.innerText = "✅ Exported database backup JSON successfully!";
      } catch (err) {
        alert("Export failed: " + err.message);
      }
    });
  }

  if (inputImport) {
    inputImport.addEventListener("change", async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      try {
        const text = await file.text();
        const data = JSON.parse(text);
        await importDatabaseFromJSON(data);
        alert("Database backup restored successfully into device memory!");
        location.reload();
      } catch (err) {
        alert("Import failed: " + err.message);
      }
    });
  }

  if (btnPush && endpointInput) {
    btnPush.addEventListener("click", async () => {
      const url = endpointInput.value.trim();
      const key = keyInput ? keyInput.value.trim() : '';
      if (!url) {
        alert("Please enter a valid Cloud Storage Endpoint URL.");
        return;
      }
      try {
        btnPush.disabled = true;
        btnPush.innerText = "Backing up...";
        await syncToCloudStorage(url, key);
        if (msgDiv) msgDiv.innerText = "✅ Data synced to Cloud Storage successfully!";
        alert("Cloud Backup complete!");
      } catch (err) {
        alert("Cloud Sync failed: " + err.message);
      } finally {
        btnPush.disabled = false;
        btnPush.innerText = "☁️ Backup to Cloud";
      }
    });
  }

  if (btnPull && endpointInput) {
    btnPull.addEventListener("click", async () => {
      const url = endpointInput.value.trim();
      const key = keyInput ? keyInput.value.trim() : '';
      if (!url) {
        alert("Please enter a valid Cloud Storage Endpoint URL.");
        return;
      }
      try {
        btnPull.disabled = true;
        btnPull.innerText = "Restoring...";
        await syncFromCloudStorage(url, key);
        if (msgDiv) msgDiv.innerText = "✅ Data restored from Cloud Storage successfully!";
        alert("Cloud Restore complete!");
        location.reload();
      } catch (err) {
        alert("Cloud Restore failed: " + err.message);
      } finally {
        btnPull.disabled = false;
        btnPull.innerText = "🔄 Restore from Cloud";
      }
    });
  }
}

// ── Tab Switching Navigation ─────────────────────────────────────────────────
window.switchTab = function(targetTab) {
  if (!targetTab) return;
  const tabBtns = document.querySelectorAll(".tab-btn");
  const tabViews = document.querySelectorAll(".tab-view");

  tabBtns.forEach(b => {
    const tabAttr = b.getAttribute("data-tab");
    if (tabAttr === targetTab || b.id === targetTab) {
      b.classList.add("active");
    } else {
      b.classList.remove("active");
    }
  });

  tabViews.forEach(v => {
    if (v.id === targetTab) {
      v.classList.add("active");
      v.style.display = "block";
    } else {
      v.classList.remove("active");
      v.style.display = "none";
    }
  });

  state.activeTab = targetTab;
};

function initNavigation() {
  const tabBtns = document.querySelectorAll(".tab-btn");
  tabBtns.forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const targetTab = btn.getAttribute("data-tab");
      if (targetTab) window.switchTab(targetTab);
    });
  });
}

// ── App Startup ──────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  try { initNavigation(); } catch (e) { console.warn("Nav init error:", e); }
  try { await initSettings(); } catch (e) { console.warn("Settings init error:", e); }
  try { initCloudSyncUI(); } catch (e) { console.warn("Cloud sync init error:", e); }
  try { await initJobsManager(); } catch (e) { console.warn("Jobs manager init error:", e); }
  try { await initPostWriter(); } catch (e) { console.warn("Post writer init error:", e); }
  try { await initVoiceRecorder(); } catch (e) { console.warn("Voice recorder init error:", e); }
  try { await initCandidateEvaluator(); } catch (e) { console.warn("Candidate evaluator init error:", e); }

  // Load initial active job into workflow context
  try {
    const jobs = await getAllJobs();
    if (jobs.length > 0) {
      workflowState.activeJob = jobs[0];
      workflowState.candidates = await getCandidatesByJob(jobs[0].job_id);
      updateAgentContextUI();
    }
  } catch (e) {
    console.warn("Context load error:", e);
  }

  // Register PWA Service Worker
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js').catch(err => console.log("SW register error:", err));
  }
});



