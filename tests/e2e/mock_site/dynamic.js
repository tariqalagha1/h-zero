// H-Zero — Mock Site Dynamic JavaScript
// Simulates a real web application with dynamic content loading

const MOCK_DATA = {
  aspirin: [
    { title: "Aspirin and Colorectal Cancer: Updated USPSTF Guidelines", journal: "Annals of Internal Medicine", date: "2024-03", evidence: "RCT, n=45,000", endpoint: "CRC incidence reduction 24%" },
    { title: "Low-Dose Aspirin for Primary Prevention: ARRIVE Trial", journal: "The Lancet", date: "2023-11", evidence: "RCT, n=12,546", endpoint: "No significant CV benefit" },
    { title: "Aspirin and Breast Cancer Recurrence", journal: "Journal of Clinical Oncology", date: "2024-01", evidence: "Cohort, n=8,200", endpoint: "HR 0.77 for recurrence" },
  ],
  cancer: [
    { title: "Immunotherapy Combinations in Advanced Melanoma", journal: "NEJM", date: "2024-05", evidence: "RCT, n=714", endpoint: "OS improvement 18 months" },
    { title: "Liquid Biopsy for Early Cancer Detection", journal: "Science", date: "2024-02", evidence: "Cohort, n=10,000", endpoint: "Sensitivity 89%, Specificity 95%" },
    { title: "CAR-T Cell Therapy in Solid Tumors", journal: "Nature Medicine", date: "2024-04", evidence: "Phase I, n=45", endpoint: "ORR 33%" },
  ],
  covid: [
    { title: "Long COVID: Pathophysiology and Management", journal: "Nature Reviews Immunology", date: "2024-06", evidence: "Review", endpoint: "Multi-system sequelae" },
    { title: "Paxlovid Effectiveness Against Omicron Subvariants", journal: "BMJ", date: "2024-03", evidence: "RCT, n=2,100", endpoint: "Hospitalization reduction 51%" },
  ],
  default: [
    { title: "No specific results. Try 'aspirin', 'cancer', or 'covid'.", journal: "", date: "", evidence: "", endpoint: "" },
  ]
};

function performSearch() {
  const query = document.getElementById('search-input').value.toLowerCase().trim();
  const resultsDiv = document.getElementById('search-results');
  const dynamicDiv = document.getElementById('dynamic-content');

  // Simulate loading
  resultsDiv.innerHTML = '<p style="color:#888;">Searching...</p>';

  setTimeout(() => {
    const data = MOCK_DATA[query] || MOCK_DATA['default'];

    if (data[0].title.includes('No specific')) {
      resultsDiv.innerHTML = `<div class="result error"><p>${data[0].title}</p></div>`;
      dynamicDiv.innerHTML = '';
      return;
    }

    let html = `<div class="result success"><p><strong>Found ${data.length} result(s)</strong> for "${query}"</p></div>`;
    html += '<table><thead><tr><th>Title</th><th>Journal</th><th>Date</th><th>Evidence</th><th>Endpoint</th></tr></thead><tbody>';

    data.forEach(row => {
      html += `<tr>
        <td>${row.title}</td>
        <td>${row.journal}</td>
        <td>${row.date}</td>
        <td>${row.evidence}</td>
        <td>${row.endpoint}</td>
      </tr>`;
    });

    html += '</tbody></table>';
    resultsDiv.innerHTML = html;

    // Add dynamic extracted data summary
    dynamicDiv.innerHTML = `
      <div class="card" style="margin-top:1rem;">
        <h3>Extracted Data Summary</h3>
        <p><strong>Query:</strong> ${query}</p>
        <p><strong>Result Count:</strong> ${data.length}</p>
        <p><strong>Study Types:</strong> ${[...new Set(data.map(d => d.evidence))].join(', ')}</p>
        <p><strong>Journals:</strong> ${[...new Set(data.map(d => d.journal))].join(', ')}</p>
        <p><strong>Earliest:</strong> ${data.sort((a,b) => a.date.localeCompare(b.date))[0]?.date || 'N/A'}</p>
      </div>
    `;
  }, 500);
}

function submitFinding(event) {
  event.preventDefault();

  const form = document.getElementById('finding-form');
  const resultDiv = document.getElementById('form-result');
  const submitBtn = document.getElementById('submit-btn');

  // Get form values
  const data = {
    title: document.getElementById('title').value,
    journal: document.getElementById('journal').value,
    studyType: document.getElementById('study-type').value,
    sampleSize: document.getElementById('sample-size').value,
    endpoint: document.getElementById('endpoint').value,
    effect: document.getElementById('effect').value,
    summary: document.getElementById('finding-summary').value,
  };

  // Simulate submission
  submitBtn.disabled = true;
  submitBtn.textContent = 'Submitting...';
  resultDiv.innerHTML = '<p style="color:#888;">Processing submission...</p>';

  setTimeout(() => {
    submitBtn.disabled = false;
    submitBtn.textContent = 'Submit Finding';
    resultDiv.innerHTML = `
      <div class="result success">
        <p><strong>✓ Finding submitted successfully!</strong></p>
        <p>Finding ID: HZ-${Date.now().toString(36).toUpperCase()}</p>
        <p>Title: ${data.title}</p>
        <p>Study Type: ${data.studyType}</p>
        <p>Status: Pending Verification</p>
      </div>
    `;
    form.reset();
  }, 800);
}

function showSection(name) {
  // Hide all sections
  document.querySelectorAll('main > section').forEach(s => s.style.display = 'none');
  // Show requested section
  const section = document.getElementById(`section-${name}`);
  if (section) {
    section.style.display = 'block';
  }
}

// Keyboard shortcut: Enter triggers search
document.getElementById('search-input')?.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') performSearch();
});

// Populate search input with window.location hash
window.addEventListener('load', () => {
  const hash = window.location.hash.replace('#', '');
  if (hash) {
    const input = document.getElementById('search-input');
    if (input) {
      input.value = hash;
      performSearch();
    }
  }
});
