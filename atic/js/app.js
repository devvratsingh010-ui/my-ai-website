/**
 * HisabAI - Kirana Store Kachha Bill OCR & Sales Dashboard Application
 */

const app = {
  token: localStorage.getItem("hisab_token") || "",
  currentUser: null,
  currentBillUnderReview: null,
  systemStatus: null,

  init: async function () {
    this.bindEvents();
    await this.ensureAuthentication();
    await this.loadSystemStatus();
    await this.loadSamples();
    await this.loadDashboard();
    await this.loadBillsHistory();
  },

  // ---------------------------------------------------------------------------
  // Authentication & Shop Switching
  // ---------------------------------------------------------------------------
  ensureAuthentication: async function () {
    if (!this.token) {
      await this.loginUser("ramesh", "kirana123");
    } else {
      try {
        const resp = await this.apiGet("/api/auth/me");
        if (resp && resp.user) {
          this.currentUser = resp.user;
          this.updateHeaderShopUI();
        } else {
          await this.loginUser("ramesh", "kirana123");
        }
      } catch (e) {
        await this.loginUser("ramesh", "kirana123");
      }
    }
  },

  loginUser: async function (username, password) {
    try {
      const resp = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const data = await resp.json();
      if (data.token) {
        this.token = data.token;
        localStorage.setItem("hisab_token", data.token);
        this.currentUser = data.user;
        this.updateHeaderShopUI();
      }
    } catch (e) {
      console.error("Login failed", e);
    }
  },

  switchShop: async function () {
    const nextUser = this.currentUser && this.currentUser.username === "ramesh" ? "suresh" : "ramesh";
    await this.loginUser(nextUser, "kirana123");
    await this.loadDashboard();
    await this.loadBillsHistory();
    alert(`Switched to: ${this.currentUser.shop_name} (${this.currentUser.full_name})`);
  },

  updateHeaderShopUI: function () {
    if (this.currentUser) {
      document.getElementById("shopNameText").textContent = this.currentUser.shop_name || "Kirana Store";
      document.getElementById("userNameText").textContent = this.currentUser.full_name || "Shopkeeper";
    }
  },

  // ---------------------------------------------------------------------------
  // API Fetch Helper
  // ---------------------------------------------------------------------------
  apiGet: async function (url) {
    const resp = await fetch(url, {
      headers: { Authorization: `Bearer ${this.token}` },
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw err;
    }
    return await resp.json();
  },

  apiPost: async function (url, body) {
    const isFormData = body instanceof FormData;
    const headers = { Authorization: `Bearer ${this.token}` };
    if (!isFormData) {
      headers["Content-Type"] = "application/json";
    }

    const resp = await fetch(url, {
      method: "POST",
      headers,
      body: isFormData ? body : JSON.stringify(body),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      throw data;
    }
    return data;
  },

  apiDelete: async function (url) {
    const resp = await fetch(url, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${this.token}` },
    });
    return await resp.json();
  },

  // ---------------------------------------------------------------------------
  // Navigation & Tabs
  // ---------------------------------------------------------------------------
  showTab: function (tabId) {
    document.querySelectorAll(".tab-pane").forEach((pane) => {
      pane.style.display = "none";
      pane.classList.remove("active");
    });
    document.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.classList.remove("active");
      if (btn.getAttribute("data-tab") === tabId) {
        btn.classList.add("active");
      }
    });
    const target = document.getElementById(tabId);
    if (target) {
      target.style.display = "block";
      target.classList.add("active");
    }

    if (tabId === "dashboardTab") {
      this.loadDashboard();
    } else if (tabId === "billsHistoryTab") {
      this.loadBillsHistory();
    }
  },

  // ---------------------------------------------------------------------------
  // System Status & OCR Credential Notice
  // ---------------------------------------------------------------------------
  loadSystemStatus: async function () {
    try {
      const status = await this.apiGet("/api/status");
      this.systemStatus = status;

      const ocr = status.ocr_status || {};
      const banner = document.getElementById("globalOcrBanner");
      const bannerText = document.getElementById("bannerText");
      const bannerIcon = document.getElementById("bannerIcon");

      const configDetails = document.getElementById("ocrConfigDetails");
      if (configDetails) {
        configDetails.innerHTML = `
          <p><strong>Provider:</strong> ${ocr.provider || "Google Cloud Vision OCR"}</p>
          <p><strong>Document Feature:</strong> ${ocr.feature || "DOCUMENT_TEXT_DETECTION"}</p>
          <p><strong>Configured:</strong> ${ocr.is_configured ? '<span class="badge-tag badge-success">Live API Active</span>' : '<span class="badge-tag badge-warning">Credentials Missing (Offline Mode Active)</span>'}</p>
          <p><strong>Auth Method:</strong> ${ocr.auth_method || "NONE"}</p>
          <div style="margin-top: 0.75rem; padding: 0.5rem; background: #fff; border: 1px solid var(--border); border-radius: var(--radius-sm);">
            <p style="font-size: 0.8rem; color: var(--text-muted);">${ocr.setup_instructions}</p>
          </div>
        `;
      }

      if (!ocr.is_configured) {
        banner.className = "alert alert-warning";
        banner.style.display = "flex";
        bannerIcon.textContent = "⚠️";
        bannerText.innerHTML = `
          <strong>Google Cloud Vision Credentials Not Configured:</strong> 
          Set <code>GOOGLE_VISION_API_KEY</code> in environment variables or <code>.env</code> file. 
          You can test the entire workflow with the built-in representative test bills below or enter bills manually.
        `;
      } else {
        banner.className = "alert alert-success";
        banner.style.display = "flex";
        bannerIcon.textContent = "✅";
        bannerText.innerHTML = `<strong>Google Cloud Vision OCR Active:</strong> Document text recognition ready for English, Hindi, Kannada, and Telugu bills.`;
      }
    } catch (e) {
      console.error("Failed to load status", e);
    }
  },

  // ---------------------------------------------------------------------------
  // Load Quick Test Samples
  // ---------------------------------------------------------------------------
  loadSamples: async function () {
    try {
      const res = await this.apiGet("/api/test-samples");
      const container = document.getElementById("sampleChipsList");
      if (!container || !res.samples) return;

      container.innerHTML = "";
      res.samples.forEach((sample) => {
        const btn = document.createElement("button");
        btn.className = "chip-btn";
        btn.innerHTML = `${sample.title}`;
        btn.title = sample.description;
        btn.onclick = () => this.scanSample(sample.id, sample.language);
        container.appendChild(btn);
      });
    } catch (e) {
      console.error("Failed to load test samples", e);
    }
  },

  // ---------------------------------------------------------------------------
  // Bill Scanning & Upload
  // ---------------------------------------------------------------------------
  scanSample: async function (sampleId, lang) {
    document.getElementById("billLanguageSelect").value = lang || "auto";
    await this.processScan({ sample_id: sampleId, language: lang || "auto" });
  },

  scanUploadedFile: async function (file) {
    const lang = document.getElementById("billLanguageSelect").value;
    const formData = new FormData();
    formData.append("image", file);
    formData.append("language", lang);
    await this.processScan(formData);
  },

  processScan: async function (payload) {
    const spinner = document.getElementById("uploadSpinner");
    spinner.style.display = "block";

    try {
      const result = await this.apiPost("/api/bills/scan", payload);
      spinner.style.display = "none";

      if (result.success && result.bill) {
        this.openVerificationScreen(result.bill);
      }
    } catch (err) {
      spinner.style.display = "none";
      const msg = err.message || "Failed to scan bill. Please try again or enter manually.";
      alert(`Scan Error: ${msg}`);
    }
  },

  // ---------------------------------------------------------------------------
  // Verification Screen
  // ---------------------------------------------------------------------------
  openVerificationScreen: function (bill) {
    this.currentBillUnderReview = bill;

    // Show Verify tab button in nav
    const navBtn = document.getElementById("navVerifyBtn");
    navBtn.style.display = "inline-flex";
    this.showTab("verifyTab");

    // Populate image preview
    const imgEl = document.getElementById("verifyImagePreview");
    imgEl.src = bill.image_path || "";
    document.getElementById("imgHashText").textContent = `Hash: ${bill.image_hash ? bill.image_hash.slice(0, 12) + "..." : "Manual"}`;

    // Raw OCR text container
    const rawOcrContainer = document.getElementById("rawOcrContainer");
    rawOcrContainer.textContent = bill.ocr_raw_text || "(No raw OCR text)";
    rawOcrContainer.style.display = "none";
    document.getElementById("toggleRawOcrBtn").textContent = "Show Raw OCR Text";

    // Image quality indicator
    const qualityEl = document.getElementById("imageQualityIndicator");
    if (bill.image_quality && bill.image_quality.is_blurry) {
      qualityEl.className = "badge-tag badge-warning";
      qualityEl.textContent = "⚠️ Blurry Image Detected";
    } else {
      qualityEl.className = "badge-tag badge-success";
      qualityEl.textContent = "Good Readability";
    }

    // Language Badge
    const langBadge = document.getElementById("detectedLangBadge");
    const langNames = { en: "English", hi: "Hindi (हिंदी)", kn: "Kannada (ಕನ್ನಡ)", te: "Telugu (తెలుగు)" };
    const primaryName = langNames[bill.detected_language] || bill.detected_language || "Auto";
    if (bill.is_mixed_language) {
      langBadge.textContent = `Mixed: ${primaryName} + English`;
      langBadge.className = "badge-tag badge-info";
    } else {
      langBadge.textContent = `Language: ${primaryName}`;
      langBadge.className = "badge-tag badge-success";
    }

    // Review Alert Box
    const alertBox = document.getElementById("verifyAlertBox");
    const alertText = document.getElementById("verifyAlertText");
    const reviewWarningBadge = document.getElementById("reviewWarningBadge");

    if (bill.needs_review && bill.review_reasons && bill.review_reasons.length > 0) {
      alertBox.style.display = "flex";
      reviewWarningBadge.style.display = "inline-block";
      alertText.innerHTML = "<strong>Please review highlighted items:</strong><br>• " + bill.review_reasons.join("<br>• ");
    } else {
      alertBox.style.display = "none";
      reviewWarningBadge.style.display = "none";
    }

    // Duplicate submission warning
    if (bill.duplicate_warning) {
      alertBox.style.display = "flex";
      alertBox.className = "alert alert-warning";
      alertText.innerHTML = `<strong>Possible Duplicate:</strong> A bill with this image or details already exists in your records from ${bill.duplicate_warning.existing_bill.bill_date}. Please double-check before saving.`;
    }

    // Fill metadata fields
    document.getElementById("verifyBillNo").value = bill.bill_number || "";
    document.getElementById("verifyBillDate").value = bill.bill_date || new Date().toISOString().split("T")[0];
    document.getElementById("verifyDiscount").value = bill.discount || 0.0;
    document.getElementById("verifyTax").value = bill.tax || 0.0;
    document.getElementById("verifyGrandTotal").value = bill.grand_total || 0.0;
    document.getElementById("verifyNotes").value = bill.notes || "";

    // Render items table
    this.renderVerifyItemsTable(bill.items || []);
    this.recalculateVerifyTotals();
  },

  renderVerifyItemsTable: function (items) {
    const tbody = document.getElementById("verifyItemsTbody");
    tbody.innerHTML = "";

    const unitsList = ["kg", "g", "ltr", "ml", "packet", "pcs", "box", "bag", "dozen"];

    items.forEach((item, index) => {
      const tr = document.createElement("tr");
      if (item.needs_review) {
        tr.className = "flagged";
      }

      const unitOptions = unitsList
        .map((u) => `<option value="${u}" ${item.unit === u ? "selected" : ""}>${u}</option>`)
        .join("");

      tr.innerHTML = `
        <td>
          <input type="text" class="item-input original-name-input ${item.needs_review && !item.item_name_original ? "flagged-input" : ""}" 
                 value="${this.escapeHtml(item.item_name_original || "")}" 
                 placeholder="Item Name (Original Script)" 
                 onchange="app.onItemFieldChange(${index}, 'item_name_original', this.value)">
          ${
            item.item_name_standard
              ? `<div style="font-size: 0.7rem; color: var(--primary); margin-top: 2px;">Standard: <strong>${item.item_name_standard}</strong></div>`
              : ""
          }
          ${
            item.review_reason
              ? `<div style="font-size: 0.7rem; color: #d97706; margin-top: 2px;">⚠️ ${this.escapeHtml(item.review_reason)}</div>`
              : ""
          }
        </td>
        <td>
          <input type="number" step="0.01" class="item-input qty-input ${item.quantity === null || item.quantity === undefined ? "flagged-input" : ""}" 
                 value="${item.quantity !== null && item.quantity !== undefined ? item.quantity : ""}" 
                 placeholder="Qty" 
                 onchange="app.onItemFieldChange(${index}, 'quantity', this.value)">
        </td>
        <td>
          <select class="item-input" onchange="app.onItemFieldChange(${index}, 'unit', this.value)">
            <option value="">-- Unit --</option>
            ${unitOptions}
          </select>
        </td>
        <td>
          <input type="number" step="0.01" class="item-input price-input ${item.unit_price === null || item.unit_price === undefined ? "flagged-input" : ""}" 
                 value="${item.unit_price !== null && item.unit_price !== undefined ? item.unit_price : ""}" 
                 placeholder="Rate" 
                 onchange="app.onItemFieldChange(${index}, 'unit_price', this.value)">
        </td>
        <td>
          <input type="number" step="0.01" class="item-input total-input ${item.line_total === null || item.line_total === undefined ? "flagged-input" : ""}" 
                 value="${item.line_total !== null && item.line_total !== undefined ? item.line_total : ""}" 
                 placeholder="Total" 
                 onchange="app.onItemFieldChange(${index}, 'line_total', this.value)">
        </td>
        <td style="text-align: center;">
          <button class="btn btn-danger-outline btn-sm" onclick="app.removeVerifyItemRow(${index})" title="Delete row">✕</button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  },

  onItemFieldChange: function (index, field, value) {
    if (!this.currentBillUnderReview || !this.currentBillUnderReview.items) return;
    const item = this.currentBillUnderReview.items[index];
    if (!item) return;

    if (field === "quantity" || field === "unit_price" || field === "line_total") {
      item[field] = value === "" ? null : parseFloat(value);
    } else {
      item[field] = value;
    }

    // Auto-calculate line total if qty and price exist
    if (field === "quantity" || field === "unit_price") {
      if (item.quantity !== null && item.unit_price !== null) {
        item.line_total = Math.round(item.quantity * item.unit_price * 100) / 100;
        const row = document.querySelectorAll("#verifyItemsTbody tr")[index];
        if (row) {
          const totInput = row.querySelector(".total-input");
          if (totInput) totInput.value = item.line_total;
        }
      }
    }

    this.recalculateVerifyTotals();
  },

  addVerifyItemRow: function () {
    if (!this.currentBillUnderReview) {
      this.currentBillUnderReview = { items: [] };
    }
    const newItem = {
      id: "item_" + Math.random().toString(36).substr(2, 8),
      item_name_original: "",
      item_name_standard: null,
      quantity: 1,
      unit: "kg",
      unit_price: null,
      line_total: null,
      needs_review: false,
    };
    this.currentBillUnderReview.items.push(newItem);
    this.renderVerifyItemsTable(this.currentBillUnderReview.items);
  },

  removeVerifyItemRow: function (index) {
    if (!this.currentBillUnderReview || !this.currentBillUnderReview.items) return;
    this.currentBillUnderReview.items.splice(index, 1);
    this.renderVerifyItemsTable(this.currentBillUnderReview.items);
    this.recalculateVerifyTotals();
  },

  recalculateVerifyTotals: function () {
    if (!this.currentBillUnderReview) return;
    const items = this.currentBillUnderReview.items || [];
    let subtotal = 0;
    items.forEach((it) => {
      if (it.line_total !== null && it.line_total !== undefined) {
        subtotal += parseFloat(it.line_total) || 0;
      }
    });
    subtotal = Math.round(subtotal * 100) / 100;

    const discount = parseFloat(document.getElementById("verifyDiscount").value) || 0.0;
    const tax = parseFloat(document.getElementById("verifyTax").value) || 0.0;
    const calculatedGrandTotal = Math.round((subtotal - discount + tax) * 100) / 100;

    document.getElementById("verifySubtotal").value = subtotal;

    const grandTotalInput = document.getElementById("verifyGrandTotal");
    const currentGrandTotal = parseFloat(grandTotalInput.value);

    // If grand total is empty or 0, auto-fill calculated total
    if (isNaN(currentGrandTotal) || currentGrandTotal === 0) {
      grandTotalInput.value = calculatedGrandTotal;
    }

    const mathNotice = document.getElementById("mathValidationNotice");
    if (Math.abs(parseFloat(grandTotalInput.value) - calculatedGrandTotal) > 0.05) {
      mathNotice.innerHTML = `⚠️ <strong style="color: #d97706;">Notice:</strong> Grand total (₹${grandTotalInput.value}) differs from items sum (₹${subtotal}) - discount (₹${discount}) + tax (₹${tax}) = ₹${calculatedGrandTotal}.`;
    } else {
      mathNotice.innerHTML = `✅ Arithmetic verified: ₹${subtotal} - ₹${discount} + ₹${tax} = ₹${calculatedGrandTotal}`;
      mathNotice.style.color = "var(--success)";
    }
  },

  confirmAndSaveBill: async function () {
    if (!this.currentBillUnderReview) return;

    const billDate = document.getElementById("verifyBillDate").value;
    const billNumber = document.getElementById("verifyBillNo").value.trim();
    const grandTotal = parseFloat(document.getElementById("verifyGrandTotal").value);
    const subtotal = parseFloat(document.getElementById("verifySubtotal").value);
    const discount = parseFloat(document.getElementById("verifyDiscount").value) || 0.0;
    const tax = parseFloat(document.getElementById("verifyTax").value) || 0.0;
    const notes = document.getElementById("verifyNotes").value.trim();

    if (!billDate) {
      alert("Please enter a valid bill date.");
      return;
    }
    if (isNaN(grandTotal) || grandTotal <= 0) {
      alert("Please verify the Grand Total amount.");
      return;
    }

    const items = this.currentBillUnderReview.items || [];
    if (items.length === 0) {
      alert("The bill must have at least one item row.");
      return;
    }

    // Validate item names
    for (let i = 0; i < items.length; i++) {
      if (!items[i].item_name_original || !items[i].item_name_original.trim()) {
        alert(`Item #${i + 1} has an empty name. Please enter the name or remove the row.`);
        return;
      }
    }

    const saveSpinner = document.getElementById("saveBtnSpinner");
    saveSpinner.style.display = "inline-block";

    const payload = {
      bill: {
        id: this.currentBillUnderReview.id,
        bill_number: billNumber || null,
        bill_date: billDate,
        subtotal: subtotal,
        discount: discount,
        tax: tax,
        grand_total: grandTotal,
        image_path: this.currentBillUnderReview.image_path || null,
        image_hash: this.currentBillUnderReview.image_hash || null,
        detected_language: this.currentBillUnderReview.detected_language || "en",
        language_used: document.getElementById("billLanguageSelect").value,
        ocr_raw_text: this.currentBillUnderReview.ocr_raw_text || "",
        notes: notes || null,
      },
      items: items,
    };

    try {
      const resp = await this.apiPost("/api/bills/verify-and-save", payload);
      saveSpinner.style.display = "none";

      if (resp.success) {
        alert("✅ " + resp.message);
        // Hide review tab
        document.getElementById("navVerifyBtn").style.display = "none";
        this.currentBillUnderReview = null;
        // Go directly to Dashboard to show updated sales
        this.showTab("dashboardTab");
      }
    } catch (err) {
      saveSpinner.style.display = "none";
      if (err.code === "DUPLICATE_BILL") {
        const force = confirm("⚠️ Duplicate Bill Detected:\n" + err.message + "\n\nDo you still wish to save this bill anyway?");
        if (force) {
          payload.force_save = true;
          const retryResp = await this.apiPost("/api/bills/verify-and-save", payload);
          if (retryResp.success) {
            alert("✅ Bill saved successfully.");
            document.getElementById("navVerifyBtn").style.display = "none";
            this.currentBillUnderReview = null;
            this.showTab("dashboardTab");
          }
        }
      } else {
        alert("Failed to save bill: " + (err.message || JSON.stringify(err)));
      }
    }
  },

  // ---------------------------------------------------------------------------
  // Sales Dashboard View
  // ---------------------------------------------------------------------------
  loadDashboard: async function () {
    try {
      const data = await this.apiGet("/api/dashboard");
      const metrics = data.metrics || {};

      document.getElementById("kpiTodaySales").textContent = `₹${(metrics.today_sales || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
      document.getElementById("kpiTodayBills").textContent = `${metrics.today_bills_count || 0} bills recorded today`;
      document.getElementById("kpiWeekSales").textContent = `₹${(metrics.this_week_sales || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
      document.getElementById("kpiMonthSales").textContent = `₹${(metrics.this_month_sales || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
      document.getElementById("kpiAllTimeSales").textContent = `₹${(metrics.all_time_sales || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
      document.getElementById("kpiTotalBills").textContent = `${metrics.total_bills_count || 0} verified bills`;

      // Render Item-wise Sales
      const itemTbody = document.getElementById("itemSalesTbody");
      itemTbody.innerHTML = "";
      const items = data.item_wise_sales || [];
      if (items.length === 0) {
        itemTbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No items recorded yet.</td></tr>`;
      } else {
        items.forEach((it) => {
          const tr = document.createElement("tr");
          tr.innerHTML = `
            <td>
              <strong>${this.escapeHtml(it.original_name)}</strong>
              ${it.item_name !== it.original_name ? `<div style="font-size: 0.75rem; color: var(--primary);">${this.escapeHtml(it.item_name)}</div>` : ""}
            </td>
            <td>${it.total_quantity} ${it.unit}</td>
            <td style="font-weight: 700; color: #0f2b48;">₹${it.total_revenue.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</td>
            <td>₹${it.avg_price} / ${it.unit}</td>
          `;
          itemTbody.appendChild(tr);
        });
      }

      // Render Recent Bills
      const recentTbody = document.getElementById("recentBillsTbody");
      recentTbody.innerHTML = "";
      const recentBills = data.recent_bills || [];
      if (recentBills.length === 0) {
        recentTbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No bills saved yet.</td></tr>`;
      } else {
        recentBills.forEach((b) => {
          const tr = document.createElement("tr");
          tr.innerHTML = `
            <td>${b.bill_date}</td>
            <td>${b.bill_number ? "#" + b.bill_number : "—"}</td>
            <td>${b.item_count} items</td>
            <td style="font-weight: 700; color: #0f2b48;">₹${parseFloat(b.grand_total).toLocaleString("en-IN", { minimumFractionDigits: 2 })}</td>
            <td>
              <button class="btn btn-outline btn-sm" onclick="app.viewBillDetails('${b.id}')">View</button>
              <button class="btn btn-danger-outline btn-sm" onclick="app.deleteBill('${b.id}')">🗑️</button>
            </td>
          `;
          recentTbody.appendChild(tr);
        });
      }
    } catch (e) {
      console.error("Failed to load dashboard", e);
    }
  },

  // ---------------------------------------------------------------------------
  // Bills History View
  // ---------------------------------------------------------------------------
  loadBillsHistory: async function () {
    try {
      const data = await this.apiGet("/api/bills");
      const tbody = document.getElementById("allBillsTbody");
      tbody.innerHTML = "";
      const bills = data.bills || [];
      if (bills.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 2rem;">No bills recorded yet.</td></tr>`;
        return;
      }
      bills.forEach((b) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td><strong>${b.bill_date}</strong></td>
          <td>${b.bill_number ? "#" + b.bill_number : "—"}</td>
          <td><span class="badge-tag badge-info">${(b.detected_language || "en").toUpperCase()}</span></td>
          <td>${b.item_count} items</td>
          <td style="font-weight: 700; color: #0f2b48;">₹${parseFloat(b.grand_total).toLocaleString("en-IN", { minimumFractionDigits: 2 })}</td>
          <td style="font-size: 0.8rem; color: var(--text-muted);">${b.created_at}</td>
          <td>
            <button class="btn btn-outline btn-sm" onclick="app.viewBillDetails('${b.id}')">View</button>
            <button class="btn btn-danger-outline btn-sm" onclick="app.deleteBill('${b.id}')">Delete</button>
          </td>
        `;
        tbody.appendChild(tr);
      });
    } catch (e) {
      console.error("Failed to load bills history", e);
    }
  },

  viewBillDetails: async function (billId) {
    try {
      const res = await this.apiGet(`/api/bills/${billId}`);
      const b = res.bill;
      if (!b) return;

      document.getElementById("modalBillTitle").textContent = `Bill #${b.bill_number || b.id} (${b.bill_date})`;
      const itemsHtml = (b.items || [])
        .map(
          (it) => `
        <tr>
          <td><strong>${this.escapeHtml(it.item_name_original)}</strong></td>
          <td>${it.quantity || "1"} ${it.unit || ""}</td>
          <td>₹${it.unit_price || "—"}</td>
          <td style="font-weight: 600;">₹${it.line_total || "—"}</td>
        </tr>
      `
        )
        .join("");

      document.getElementById("modalBillContent").innerHTML = `
        <div style="margin-bottom: 1rem;">
          <p><strong>Shop:</strong> ${this.currentUser.shop_name}</p>
          <p><strong>Date:</strong> ${b.bill_date}</p>
          <p><strong>Language:</strong> ${(b.detected_language || "en").toUpperCase()}</p>
          ${b.image_path ? `<div style="margin: 0.75rem 0;"><img src="${b.image_path}" style="max-height: 200px; border-radius: var(--radius-sm); border: 1px solid var(--border);"></div>` : ""}
        </div>
        <table class="items-table" style="margin-bottom: 1rem;">
          <thead><tr><th>Item</th><th>Qty</th><th>Rate</th><th>Total</th></tr></thead>
          <tbody>${itemsHtml}</tbody>
        </table>
        <div style="background: #f8fafc; padding: 0.75rem; border-radius: var(--radius-sm); text-align: right;">
          <p>Subtotal: ₹${b.subtotal || b.grand_total}</p>
          <p>Discount: ₹${b.discount || 0}</p>
          <p>Tax: ₹${b.tax || 0}</p>
          <p style="font-size: 1.1rem; font-weight: 800; color: #0f2b48;">Grand Total: ₹${b.grand_total}</p>
        </div>
      `;
      document.getElementById("billModal").style.display = "flex";
    } catch (e) {
      alert("Failed to fetch bill details");
    }
  },

  deleteBill: async function (billId) {
    if (!confirm("Are you sure you want to delete this bill? This will update your sales totals immediately.")) {
      return;
    }
    try {
      const resp = await this.apiDelete(`/api/bills/${billId}`);
      if (resp.success) {
        alert("Bill deleted successfully. Sales metrics recalculated.");
        await this.loadDashboard();
        await this.loadBillsHistory();
      }
    } catch (e) {
      alert("Failed to delete bill.");
    }
  },

  closeModal: function () {
    document.getElementById("billModal").style.display = "none";
  },

  escapeHtml: function (str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  },

  // ---------------------------------------------------------------------------
  // Event Bindings
  // ---------------------------------------------------------------------------
  bindEvents: function () {
    // Nav tab clicks
    document.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const tabId = btn.getAttribute("data-tab");
        this.showTab(tabId);
      });
    });

    // File input change
    const fileInput = document.getElementById("billFileInput");
    fileInput.addEventListener("change", (e) => {
      if (e.target.files && e.target.files[0]) {
        this.scanUploadedFile(e.target.files[0]);
      }
    });

    // Drag and drop
    const dropZone = document.getElementById("dropZone");
    dropZone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropZone.classList.add("dragover");
    });
    dropZone.addEventListener("dragleave", () => {
      dropZone.classList.remove("dragover");
    });
    dropZone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropZone.classList.remove("dragover");
      if (e.dataTransfer.files && e.dataTransfer.files[0]) {
        this.scanUploadedFile(e.dataTransfer.files[0]);
      }
    });

    // Switch Shop button
    document.getElementById("switchShopBtn").addEventListener("click", () => {
      this.switchShop();
    });

    // Manual entry button
    document.getElementById("manualEntryBtn").addEventListener("click", () => {
      this.openVerificationScreen({
        id: "bill_" + Math.random().toString(36).substr(2, 8),
        bill_date: new Date().toISOString().split("T")[0],
        bill_number: "",
        subtotal: 0.0,
        discount: 0.0,
        tax: 0.0,
        grand_total: 0.0,
        detected_language: document.getElementById("billLanguageSelect").value,
        items: [
          {
            id: "item_1",
            item_name_original: "",
            quantity: 1,
            unit: "kg",
            unit_price: 0.0,
            line_total: 0.0,
            needs_review: false,
          },
        ],
        needs_review: false,
      });
    });

    // Verification screen events
    document.getElementById("addItemRowBtn").addEventListener("click", () => {
      this.addVerifyItemRow();
    });
    document.getElementById("confirmSaveBillBtn").addEventListener("click", () => {
      this.confirmAndSaveBill();
    });
    document.getElementById("cancelVerifyBtn").addEventListener("click", () => {
      this.showTab("scanTab");
    });

    // Raw OCR toggle
    document.getElementById("toggleRawOcrBtn").addEventListener("click", () => {
      const el = document.getElementById("rawOcrContainer");
      const btn = document.getElementById("toggleRawOcrBtn");
      if (el.style.display === "none") {
        el.style.display = "block";
        btn.textContent = "Hide Raw OCR Text";
      } else {
        el.style.display = "none";
        btn.textContent = "Show Raw OCR Text";
      }
    });

    // Dashboard refresh
    document.getElementById("refreshDashboardBtn").addEventListener("click", () => {
      this.loadDashboard();
    });
    document.getElementById("refreshBillsHistoryBtn").addEventListener("click", () => {
      this.loadBillsHistory();
    });

    // Discount/Tax/Grand total changes
    document.getElementById("verifyDiscount").addEventListener("input", () => this.recalculateVerifyTotals());
    document.getElementById("verifyTax").addEventListener("input", () => this.recalculateVerifyTotals());
    document.getElementById("verifyGrandTotal").addEventListener("input", () => this.recalculateVerifyTotals());
  },
};

// Initialize on DOM load
document.addEventListener("DOMContentLoaded", () => {
  app.init();
});
