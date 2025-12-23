console.log("ICodex web app loaded.");

async function startAdaptive(assignmentId, box) {
  box.innerHTML = `<p class="muted">Starting...</p>`;
  const form = new FormData();
  form.append("assignment_id", assignmentId);
  const res = await fetch("/student/start_adaptive", { method: "POST", body: form });
  if (!res.ok) {
    box.innerHTML = `<p class="muted">Failed to start.</p>`;
    return;
  }
  const data = await res.json();
  renderQuestion(box, assignmentId, data.question, data.remaining);
}

async function submitAdaptive(assignmentId, answer, box, remaining) {
  const form = new FormData();
  form.append("assignment_id", assignmentId);
  form.append("student_answer", answer);
  form.append("time_taken", "15");
  form.append("expected_time", "20");
  form.append("difficulty", "medium");
  const res = await fetch("/student/answer_adaptive", { method: "POST", body: form });
  if (!res.ok) {
    box.innerHTML = `<p class="muted">Submit failed.</p>`;
    return;
  }
  const data = await res.json();
  if (data.done) {
    box.innerHTML = `<p class="muted">Done. Score ${data.score}/${data.answered}</p>`;
    return;
  }
  renderQuestion(box, assignmentId, data.next_question, data.remaining);
}

function renderQuestion(box, assignmentId, q, remaining) {
  const opts = q.options || [];
  const optHtml = opts.length
    ? opts
        .map(
          (o, idx) =>
            `<label class="opt"><input type="radio" name="ans-${assignmentId}" value="${o}"> ${o}</label>`
        )
        .join("")
    : `<textarea name="ans-${assignmentId}" rows="3" placeholder="Type your answer"></textarea>`;

  box.innerHTML = `
    <div class="qhead"><strong>Remaining: ${remaining}</strong></div>
    <p>${q.question}</p>
    <div class="options">${optHtml}</div>
    <button type="button" class="submit-test" data-assignment="${assignmentId}">Submit & Next</button>
  `;
}

document.addEventListener("click", (e) => {
  if (e.target.classList.contains("start-test")) {
    const assignmentId = e.target.dataset.assignment;
    const wrapper = e.target.closest(".card");
    const box = wrapper.querySelector(".question-box");
    startAdaptive(assignmentId, box);
  }
  if (e.target.classList.contains("submit-test")) {
    const assignmentId = e.target.dataset.assignment;
    const wrapper = e.target.closest(".card");
    const box = wrapper.querySelector(".question-box");
    const radios = box.querySelectorAll(`input[name="ans-${assignmentId}"]`);
    let val = "";
    radios.forEach((r) => {
      if (r.checked) val = r.value;
    });
    if (!val) {
      const ta = box.querySelector("textarea");
      if (ta) val = ta.value;
    }
    if (!val) {
      alert("Please provide an answer.");
      return;
    }
    submitAdaptive(assignmentId, val, box);
  }
});
