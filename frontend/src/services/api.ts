import { safeStorage } from "./storage";
import type { TenderDetail, SourceDocumentItem } from "../types/tender";

// ============================================================================
// Configuration
// ============================================================================

const BACKEND_URL = "http://localhost:8000";
const STORAGE_KEY = "tender_volks_mock_data_v3";

// ============================================================================
// Mock data — used ONLY when backend is unreachable
// ============================================================================

const initialTenders: TenderDetail[] = [
  {
    id: "PWD-BRIDGE-2026-081",
    title: "Construction of Major Bridge over Sakarboga River on Raipur-Bilaspur Expressway",
    authorityName: "Public Works Department Chhattisgarh",
    deadline: "2026-07-28T17:00:00Z",
    tenderValue: "2.44 Crore",
    emdAmount: "4.88 Lakh",
    tenderFee: "5,000 INR",
    location: "Bilaspur, Chhattisgarh",
    description: "Civil tender for foundations, piers, mounting abutments, structural railing walls and approach road bridge segments.",
    parse_status: "completed",
    parse_confidence: 94.2,
    review_status: "completed",
    reviewer_name: "Yuvraj Sharma",
    issues_count: 1,
    location_city: "Bilaspur",
    location_state: "Chhattisgarh",
    sector: "Infrastructure",
    snippet: "Civil tender for Raipur-Bilaspur Expressway bridge construction over Sakarboga River, involving pre-stressed concrete girders.",
    updated_at: "Jul 28, 2026",
    documents: {
      sourceDocuments: [
        {
          id: "doc-pwd-001",
          name: "PWD_Railing_Bridge_Raipur_Sakarboga.pdf",
          kind: "pdf",
          origin: "source",
          url: "/storage/jobs/job-sakarboga/PWD_Railing_Bridge_Raipur_Sakarboga.pdf",
          previewUrl: undefined,
          downloadable: true,
          openable: true,
          createdAt: "2026-07-01T10:00:00Z",
          reviewState: "default",
          isPrimary: true,
          uploadedBy: "Yuvraj Sharma"
        }
      ],
      generatedOutputs: [
        {
          id: "out-pwd-001",
          name: "PWD_Railing_Bridge_Raipur_Sakarboga_InfoSheet.xlsx",
          kind: "xlsx",
          origin: "generated",
          url: "/storage/jobs/job-sakarboga/PWD_Railing_Bridge_Raipur_Sakarboga_InfoSheet.xlsx",
          previewUrl: undefined,
          downloadable: true,
          openable: true,
          createdAt: "2026-07-01T10:05:00Z",
          reviewState: "default",
          generator: "ocr",
          outputKind: "info_sheet"
        }
      ],
      extractedLinkedPdfs: [
        {
          id: "link-pwd-001",
          name: "technical-specifications.pdf",
          kind: "pdf",
          origin: "linked",
          url: "https://pwd.cg.gov.in/downloads/technical-specifications.pdf",
          previewUrl: undefined,
          downloadable: true,
          openable: true,
          createdAt: "2026-07-01T10:03:00Z",
          reviewState: "default",
          extractedFromDocumentId: "doc-pwd-001",
          sourcePage: 3,
          anchorText: "All concrete mixing specifications are detailed in technical-specifications.pdf",
          extractionConfidence: 96
        },
        {
          id: "link-pwd-002",
          name: "boq-annexure.pdf",
          kind: "pdf",
          origin: "linked",
          url: "https://pwd.cg.gov.in/downloads/boq-annexure.pdf",
          previewUrl: undefined,
          downloadable: true,
          openable: true,
          createdAt: "2026-07-01T10:03:10Z",
          reviewState: "default",
          extractedFromDocumentId: "doc-pwd-001",
          sourcePage: 12,
          anchorText: "Bill of Quantities pricing guidelines are available in boq-annexure.pdf",
          extractionConfidence: 98
        },
        {
          id: "link-pwd-003",
          name: "eligibility-criteria.pdf",
          kind: "pdf",
          origin: "linked",
          url: "https://pwd.cg.gov.in/downloads/eligibility-criteria.pdf",
          previewUrl: undefined,
          downloadable: true,
          openable: true,
          createdAt: "2026-07-01T10:03:20Z",
          reviewState: "default",
          extractedFromDocumentId: "doc-pwd-001",
          sourcePage: 5,
          anchorText: "Detailed financial turnover benchmarks are listed in eligibility-criteria.pdf",
          extractionConfidence: 94
        }
      ],
      mentionedAttachments: [
        {
          id: "ment-pwd-001",
          name: "Corrigendum-II.pdf",
          kind: "pdf",
          origin: "mentioned",
          createdAt: "2026-07-01T10:03:30Z",
          reviewState: "unresolved",
          mentionText: "Amendment parameters for the site survey dimensions are declared inside Corrigendum-II.pdf.",
          sourcePage: 8,
          resolved: false
        }
      ]
    },
    infoSheetSections: [
      {
        id: "sec-pwd-1",
        title: "Basic Information",
        fields: [
          {
            id: "fp-1",
            label: "Tender Name",
            value: "Construction of Major Bridge over Sakarboga River on Raipur-Bilaspur Expressway",
            confidence: 98,
            critical: true,
            sourcePage: 1,
            sourceSnippet: "Raipur-Bilaspur Expressway Sakarboga bridge contract details.",
            status: "verified"
          },
          {
            id: "fp-2",
            label: "Reference ID",
            value: "PWD/BRIDGE/56277502",
            confidence: 99,
            critical: true,
            sourcePage: 1,
            sourceSnippet: "NIT No: PWD/BRIDGE/56277502",
            status: "verified"
          }
        ]
      },
      {
        id: "sec-pwd-2",
        title: "Pricing & Finance",
        fields: [
          {
            id: "fp-3",
            label: "Tender Value",
            value: "2,44,00,000 INR",
            confidence: 96,
            critical: true,
            sourcePage: 1,
            sourceSnippet: "Estimated cost of Raipur Sakarboga bridge project is INR 2.44 Crores.",
            status: "verified"
          },
          {
            id: "fp-4",
            label: "EMD Amount",
            value: "4,88,000 INR",
            confidence: 97,
            critical: true,
            sourcePage: 1,
            sourceSnippet: "EMD deposit required represents 4,88,000.",
            status: "verified"
          }
        ]
      }
    ],
    rawTextPages: [
      { page: 1, text: "Raipur-Bilaspur Expressway major bridge tenders. NIT PWD/BRIDGE/56277502." }
    ]
  },
  {
    id: "GEM-BIHAR-2026-775",
    title: "Drainage works and sewerage layout segment setup for newly built shelter home in Supaul",
    authorityName: "Urban Development Agency Bihar",
    deadline: "2026-07-30T17:00:00Z",
    tenderValue: "1.65 Crore",
    emdAmount: "3.20 Lakh",
    tenderFee: "3,000 INR",
    location: "Supaul, Bihar",
    description: "Tender For Drainage Works For The Newly Constructed/Under-Construction Large Shelter Home In Supaul.",
    parse_status: "completed",
    parse_confidence: 68.5,
    review_status: "unreviewed",
    reviewer_name: null,
    issues_count: 2,
    location_city: "Supaul",
    location_state: "Bihar",
    sector: "Infrastructure",
    snippet: "Municipal sewer mapping, layout alignment, civil pipe connections, and leveling at Supaul central residents shelter structures.",
    updated_at: "Jul 30, 2026",
    documents: {
      sourceDocuments: [
        {
          id: "doc-bih-001",
          name: "GEM_Supaul_Drainage_Shelter.pdf",
          kind: "pdf",
          origin: "source",
          url: "/storage/jobs/job-supaul/GEM_Supaul_Drainage_Shelter.pdf",
          previewUrl: undefined,
          downloadable: true,
          openable: true,
          createdAt: "2026-07-07T12:00:00Z",
          reviewState: "default",
          isPrimary: true,
          uploadedBy: "Yuvraj Sharma"
        }
      ],
      generatedOutputs: [
        {
          id: "out-bih-001",
          name: "GEM_Supaul_Drainage_Shelter_InfoSheet.xlsx",
          kind: "xlsx",
          origin: "generated",
          url: "/storage/jobs/job-supaul/GEM_Supaul_Drainage_Shelter_InfoSheet.xlsx",
          previewUrl: undefined,
          downloadable: true,
          openable: true,
          createdAt: "2026-07-07T12:08:00Z",
          reviewState: "default",
          generator: "ocr",
          outputKind: "info_sheet"
        }
      ],
      extractedLinkedPdfs: [],
      mentionedAttachments: [
        {
          id: "ment-bih-001",
          name: "BOQ_Drainage_Supaul.xlsx",
          kind: "xlsx",
          origin: "mentioned",
          createdAt: "2026-07-07T12:08:30Z",
          reviewState: "unresolved",
          mentionText: "Bidders must fill rates only in the designated spreadsheet file (BOQ_Drainage_Supaul.xlsx).",
          sourcePage: 4,
          resolved: false
        }
      ]
    },
    infoSheetSections: [
      {
        id: "sec-bih-1",
        title: "Basic Information",
        fields: [
          {
            id: "fb-1",
            label: "Tender Name",
            value: "Sewer layout setup for shelter home in Supaul",
            confidence: 94,
            critical: true,
            sourcePage: 1,
            sourceSnippet: "Drainage works for Supaul shelter home.",
            status: "extracted"
          }
        ]
      },
      {
        id: "sec-bih-2",
        title: "Pricing Details",
        fields: [
          {
            id: "fb-2",
            label: "Tender Value",
            value: "16.50 Lakh (verify Crore specifications)",
            confidence: 45,
            critical: true,
            sourcePage: 1,
            sourceSnippet: "Project estimate is 16.50 Lakh",
            status: "extracted"
          }
        ]
      }
    ]
  }
];

// ============================================================================
// Backend connectivity & adapter layer
// ============================================================================

let _backendReachable: boolean | null = null;

/**
 * Checks if the real backend API is reachable.
 * Caches the result to avoid repeated pings.
 */
async function isBackendReachable(): Promise<boolean> {
  if (_backendReachable !== null) return _backendReachable;
  try {
    const res = await fetch(`${BACKEND_URL}/health`, { method: "GET", signal: AbortSignal.timeout(2000) });
    _backendReachable = res.ok;
  } catch {
    _backendReachable = false;
  }
  return _backendReachable;
}

/**
 * Adapts a raw backend JSON payload into a complete TenderDetail object
 * by filling in frontend-only fields with sensible defaults.
 */
/** Converts any non-string field value to its JSON string representation.
 *  The GEM extractor can return `field.value` as an array of schedule objects
 *  (e.g. [{schedule_number, consignee_name, …}]).  Rendering that directly in
 *  JSX throws "Objects are not valid as a React child", so we serialise it here
 *  at the data boundary before it ever reaches a component.
 */
function sanitiseInfoSheetSections(sections: any[]): any[] {
  if (!Array.isArray(sections)) return [];
  return sections.map((sec) => ({
    ...sec,
    fields: Array.isArray(sec.fields)
      ? sec.fields.map((f: any) => ({
          ...f,
          value:
            f.value !== null && f.value !== undefined && typeof f.value !== "string"
              ? JSON.stringify(f.value)
              : f.value,
        }))
      : [],
  }));
}

function adaptBackendPayload(raw: Record<string, unknown>): TenderDetail {
  const r = raw as Record<string, any>;
  return {
    id: r.id ?? "",
    title: r.title ?? "",
    authorityName: r.authorityName ?? "",
    department: r.department ?? "",
    deadline: r.deadline ?? "",
    tenderValue: r.tenderValue ?? "",
    emdAmount: r.emdAmount ?? "",
    tenderFee: r.tenderFee ?? "",
    location: r.location ?? "",
    description: r.description ?? "",
    documents: {
      sourceDocuments: r.documents?.sourceDocuments ?? [],
      generatedOutputs: r.documents?.generatedOutputs ?? [],
      extractedLinkedPdfs: r.documents?.extractedLinkedPdfs ?? [],
      mentionedAttachments: r.documents?.mentionedAttachments ?? [],
    },
    infoSheetSections: sanitiseInfoSheetSections(r.infoSheetSections ?? []),
    rawTextPages: r.rawTextPages ?? [],
    raw_ocr_text: r.raw_ocr_text ?? "",
    parse_status: r.parse_status ?? "pending",
    parse_confidence: r.parse_confidence ?? 0,
    review_status: r.review_status ?? "unreviewed",
    reviewer_name: r.reviewer_name ?? null,
    issues_count: r.issues_count ?? 0,
    location_city: r.location_city ?? "",
    location_state: r.location_state ?? "",
    sector: r.sector ?? "Infrastructure",
    snippet: r.snippet ?? "",
    updated_at: r.updated_at ?? "",
  } as TenderDetail;
}

// ============================================================================
// In-memory store helpers (fallback when backend is offline)
// ============================================================================

const getStoredTenders = (): TenderDetail[] => {
  const data = safeStorage.getItem(STORAGE_KEY);
  if (!data) {
    safeStorage.setItem(STORAGE_KEY, JSON.stringify(initialTenders));
    return initialTenders;
  }
  try {
    return JSON.parse(data);
  } catch {
    return initialTenders;
  }
};

const saveStoredTenders = (tenders: TenderDetail[]) => {
  safeStorage.setItem(STORAGE_KEY, JSON.stringify(tenders));
};

// ============================================================================
// API Service — tries real backend first, falls back to in-memory mock
// ============================================================================

export const apiService = {
  /**
   * Fetches all tenders.
   * Tries GET /tenders/workspace/list first. Falls back to mock data.
   */
  getTenders: async (): Promise<TenderDetail[]> => {
    try {
      if (await isBackendReachable()) {
        const res = await fetch(`${BACKEND_URL}/tenders/workspace/list`);
        if (res.ok) {
          const data = await res.json();
          const adapted = (data as Record<string, unknown>[]).map(adaptBackendPayload);
          // Merge: backend tenders first, then mock tenders that aren't duplicated
          const backendIds = new Set(adapted.map(t => t.id));
          const mockTenders = getStoredTenders().filter(t => !backendIds.has(t.id));
          return [...adapted, ...mockTenders];
        }
      }
    } catch {
      // Backend unreachable — fall through to mock
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
    return getStoredTenders();
  },

  /**
   * Gets a single tender by ID.
   */
  getTenderById: async (id: string): Promise<TenderDetail | null> => {
    try {
      if (await isBackendReachable()) {
        const res = await fetch(`${BACKEND_URL}/tenders/workspace/${id}`);
        if (res.ok) {
          return adaptBackendPayload(await res.json());
        }
      }
    } catch {
      // fall through
    }
    const tenders = getStoredTenders();
    return tenders.find((t) => t.id === id) || null;
  },

  /**
   * Updates a field value on a tender's info sheet.
   * Currently mock-only — backend endpoint can be added later.
   */
  updateTenderField: async (
    tenderId: string,
    fieldId: string,
    value: string
  ): Promise<TenderDetail> => {
    try {
      if (await isBackendReachable()) {
        const res = await fetch(`${BACKEND_URL}/tenders/workspace/${tenderId}/fields/${fieldId}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ value })
        });
        if (res.ok) {
          return adaptBackendPayload(await res.json());
        }
      }
    } catch (err) {
      console.error("Failed to update field on backend, falling back to local store:", err);
    }

    const tenders = getStoredTenders();
    const idx = tenders.findIndex((t) => t.id === tenderId);
    if (idx === -1) throw new Error("Tender not found");

    const tender = { ...tenders[idx] };
    tender.infoSheetSections = tender.infoSheetSections.map((sec) => ({
      ...sec,
      fields: sec.fields.map((f) => {
        if (f.id === fieldId) {
          return { ...f, value, status: "edited" as const };
        }
        return f;
      })
    }));

    // Update issue counts
    let issues = 0;
    tender.infoSheetSections.forEach((sec) => {
      sec.fields.forEach((f) => {
        if (f.status === "extracted" && f.confidence && f.confidence < 70) {
          issues++;
        }
      });
    });
    const unresolvedMentions = tender.documents.mentionedAttachments.filter((m) => !m.resolved).length;
    tender.issues_count = issues + unresolvedMentions;

    tenders[idx] = tender;
    saveStoredTenders(tenders);
    return tender;
  },

  /**
   * Marks a field as verified.
   */
  verifyField: async (tenderId: string, fieldId: string): Promise<TenderDetail> => {
    try {
      if (await isBackendReachable()) {
        const res = await fetch(`${BACKEND_URL}/tenders/workspace/${tenderId}/fields/${fieldId}/verify`, {
          method: "POST"
        });
        if (res.ok) {
          return adaptBackendPayload(await res.json());
        }
      }
    } catch (err) {
      console.error("Failed to verify field on backend, falling back to local store:", err);
    }

    const tenders = getStoredTenders();
    const idx = tenders.findIndex((t) => t.id === tenderId);
    if (idx === -1) throw new Error("Tender not found");

    const tender = { ...tenders[idx] };
    tender.infoSheetSections = tender.infoSheetSections.map((sec) => ({
      ...sec,
      fields: sec.fields.map((f) => {
        if (f.id === fieldId) {
          return { ...f, status: "verified" as const };
        }
        return f;
      })
    }));

    let issues = 0;
    tender.infoSheetSections.forEach((sec) => {
      sec.fields.forEach((f) => {
        if (f.status === "extracted" && f.confidence && f.confidence < 70) {
          issues++;
        }
      });
    });
    const unresolvedMentions = tender.documents.mentionedAttachments.filter((m) => !m.resolved).length;
    tender.issues_count = issues + unresolvedMentions;

    tenders[idx] = tender;
    saveStoredTenders(tenders);
    return tender;
  },

  /**
   * Uploads a tender PDF.
   * Tries POST /tenders/workspace/ingest (real backend).
   * Falls back to in-memory mock creation.
   */
  uploadTender: async (file: File): Promise<TenderDetail> => {
    // Try real backend first
    try {
      if (await isBackendReachable()) {
        const formData = new FormData();
        formData.append("file", file);
        const res = await fetch(`${BACKEND_URL}/tenders/workspace/ingest`, {
          method: "POST",
          body: formData,
        });
        if (res.ok) {
          const data = await res.json();
          const jobId = data.job_id;
          // Return a pending skeleton — the polling in App.tsx will update it
          return adaptBackendPayload({
            id: jobId,
            title: file.name.replace(/\.[^/.]+$/, "").replace(/[_-]/g, " "),
            authorityName: "",
            deadline: "",
            tenderValue: "",
            parse_status: "pending",
            parse_confidence: 0,
            review_status: "unreviewed",
            issues_count: 0,
            documents: {
              sourceDocuments: [{
                id: `src-${jobId}`,
                name: file.name,
                kind: "pdf",
                origin: "source",
                url: `/storage/jobs/${jobId}/${file.name}`,
                downloadable: true,
                openable: true,
                isPrimary: true,
                uploadedBy: "Yuvraj Sharma"
              }],
              generatedOutputs: [],
              extractedLinkedPdfs: [],
              mentionedAttachments: []
            },
            infoSheetSections: [],
            snippet: `Uploading: ${file.name}. Pipeline queued.`,
          });
        }
      }
    } catch {
      // Fall through to mock
    }

    // Mock fallback
    await new Promise((resolve) => setTimeout(resolve, 1000));
    const tenders = getStoredTenders();

    const randomId = `GEM-TENDER-${Math.floor(100000 + Math.random() * 900000)}`;
    const mockTender: TenderDetail = {
      id: randomId,
      title: file.name.replace(/\.[^/.]+$/, "").replace(/[_-]/g, " "),
      authorityName: "Extracting Department Authority...",
      deadline: new Date(Date.now() + 14 * 24 * 60 * 60 * 1000).toISOString(),
      tenderValue: "0.00",
      location: "New Delhi, Delhi",
      parse_status: "pending",
      parse_confidence: 0,
      review_status: "unreviewed",
      reviewer_name: null,
      issues_count: 0,
      location_city: "Delhi",
      location_state: "Delhi",
      sector: "Infrastructure",
      snippet: `Ingested local file: ${file.name}. Pending pipeline triggering.`,
      updated_at: new Date().toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }),
      documents: {
        sourceDocuments: [
          {
            id: `doc-${Math.random().toString(36).substring(2, 6)}`,
            name: file.name,
            kind: "pdf",
            origin: "source",
            url: URL.createObjectURL(file),
            downloadable: true,
            openable: true,
            createdAt: new Date().toISOString(),
            reviewState: "default",
            isPrimary: true,
            uploadedBy: "Yuvraj Sharma"
          }
        ],
        generatedOutputs: [
          {
            id: `out-${Math.random().toString(36).substring(2, 6)}`,
            name: `${file.name.replace(/\.[^/.]+$/, "")}_InfoSheet.xlsx`,
            kind: "xlsx",
            origin: "generated",
            url: "#",
            downloadable: true,
            openable: true,
            createdAt: new Date().toISOString(),
            reviewState: "default",
            generator: "ocr",
            outputKind: "info_sheet"
          }
        ],
        extractedLinkedPdfs: [],
        mentionedAttachments: []
      },
      infoSheetSections: []
    };

    const newTenders = [mockTender, ...tenders];
    saveStoredTenders(newTenders);
    return mockTender;
  },

  /**
   * Triggers processing on a tender.
   * With the real backend, processing is auto-triggered on upload via /workspace/ingest.
   * This mock simulates the transition for offline-mode tenders.
   */
  triggerProcessing: async (tenderId: string): Promise<TenderDetail> => {
    // If backend is reachable, processing was already triggered on upload.
    // Just return the current state.
    try {
      if (await isBackendReachable()) {
        const res = await fetch(`${BACKEND_URL}/tenders/workspace/${tenderId}`);
        if (res.ok) {
          return adaptBackendPayload(await res.json());
        }
      }
    } catch {
      // Fall through
    }

    // Mock fallback
    const tenders = getStoredTenders();
    const idx = tenders.findIndex((t) => t.id === tenderId);
    if (idx === -1) throw new Error("Tender not found");

    const tender = { ...tenders[idx] };
    tender.parse_status = "processing";
    tenders[idx] = tender;
    saveStoredTenders(tenders);

    // Simulate completion after 3 seconds
    setTimeout(() => {
      const activeTenders = getStoredTenders();
      const activeIdx = activeTenders.findIndex((t) => t.id === tenderId);
      if (activeIdx !== -1) {
        const activeTender = { ...activeTenders[activeIdx] };
        activeTender.parse_status = "completed";
        activeTender.parse_confidence = 88.5;
        activeTender.authorityName = "National Highways Development Corporation";
        activeTender.tenderValue = "12.50 Crore";
        activeTender.emdAmount = "25.00 Lakh";
        activeTender.location = "Lucknow, Uttar Pradesh";
        activeTender.location_city = "Lucknow";
        activeTender.location_state = "Uttar Pradesh";
        activeTender.snippet = `Civil construction of Lucknow Expressway service lane extensions. Estimated cost: 12.50 Cr.`;

        activeTender.infoSheetSections = [
          {
            id: "sec-1",
            title: "Basic Information",
            fields: [
              {
                id: "f-1",
                label: "Tender Name",
                value: activeTender.title,
                confidence: 91,
                critical: true,
                sourcePage: 1,
                sourceSnippet: activeTender.title,
                status: "extracted"
              }
            ]
          },
          {
            id: "sec-2",
            title: "Commercials",
            fields: [
              {
                id: "f-2",
                label: "Tender Value",
                value: "12,50,00,000 INR",
                confidence: 89,
                critical: true,
                sourcePage: 1,
                sourceSnippet: "Project estimate totals 12.50 Crore",
                status: "extracted"
              }
            ]
          }
        ];

        activeTender.documents.extractedLinkedPdfs = [
          {
            id: `link-mock-${Math.random().toString(36).substring(2, 6)}`,
            name: "technical-specifications.pdf",
            kind: "pdf",
            origin: "linked",
            url: "https://pwd.cg.gov.in/downloads/technical-specifications.pdf",
            previewUrl: undefined,
            downloadable: true,
            openable: true,
            createdAt: new Date().toISOString(),
            reviewState: "default",
            extractedFromDocumentId: activeTender.documents.sourceDocuments[0]?.id || "unknown",
            sourcePage: 3,
            anchorText: "All concrete mixing specifications are detailed in technical-specifications.pdf",
            extractionConfidence: 96
          }
        ];

        const lowConfidence = activeTender.infoSheetSections.reduce((acc, sec) =>
          acc + sec.fields.filter(f => f.status === "extracted" && f.confidence && f.confidence < 70).length, 0);
        const unresolved = activeTender.documents.mentionedAttachments.filter(m => !m.resolved).length;
        activeTender.issues_count = lowConfidence + unresolved;

        activeTenders[activeIdx] = activeTender;
        saveStoredTenders(activeTenders);
      }
    }, 3000);

    return tender;
  },

  /**
   * Marks a tender as reviewed.
   */
  markReviewed: async (tenderId: string, reviewer: string): Promise<TenderDetail> => {
    try {
      if (await isBackendReachable()) {
        const res = await fetch(`${BACKEND_URL}/tenders/workspace/${tenderId}/review`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ reviewer_name: reviewer })
        });
        if (res.ok) {
          return adaptBackendPayload(await res.json());
        }
      }
    } catch (err) {
      console.error("Failed to mark reviewed on backend, falling back to local store:", err);
    }

    const tenders = getStoredTenders();
    const idx = tenders.findIndex((t) => t.id === tenderId);
    if (idx === -1) throw new Error("Tender not found");

    const tender = { ...tenders[idx] };
    tender.review_status = "completed";
    tender.reviewer_name = reviewer;
    tender.infoSheetSections = tender.infoSheetSections.map((sec) => ({
      ...sec,
      fields: sec.fields.map((f) => ({
        ...f,
        status: f.status === "extracted" ? "verified" as const : f.status
      }))
    }));
    tender.issues_count = 0;

    tenders[idx] = tender;
    saveStoredTenders(tenders);
    return tender;
  },

  /**
   * Links a file to a mentioned attachment (resolves it).
   */
  linkDocument: async (tenderId: string, docId: string, file: File): Promise<TenderDetail> => {
    const tenders = getStoredTenders();
    const idx = tenders.findIndex((t) => t.id === tenderId);
    if (idx === -1) throw new Error("Tender not found");

    const tender = { ...tenders[idx] };
    const mentionIdx = tender.documents.mentionedAttachments.findIndex(m => m.id === docId);

    if (mentionIdx !== -1) {
      const mention = { ...tender.documents.mentionedAttachments[mentionIdx] };
      mention.resolved = true;
      mention.reviewState = "default";

      const newMentions = [...tender.documents.mentionedAttachments];
      newMentions[mentionIdx] = mention;
      tender.documents.mentionedAttachments = newMentions;

      const newAttachment: SourceDocumentItem = {
        id: `doc-${Math.random().toString(36).substring(2, 6)}`,
        name: file.name,
        kind: file.name.endsWith(".xlsx") || file.name.endsWith(".xls") ? "xlsx" : file.name.endsWith(".docx") ? "doc" : "pdf",
        origin: "source",
        url: URL.createObjectURL(file),
        downloadable: true,
        openable: true,
        createdAt: new Date().toISOString(),
        reviewState: "default",
        isPrimary: false,
        uploadedBy: "Yuvraj Sharma"
      };

      tender.documents.sourceDocuments = [...tender.documents.sourceDocuments, newAttachment];

      const lowConfidence = tender.infoSheetSections.reduce((acc, sec) =>
        acc + sec.fields.filter(f => f.status === "extracted" && f.confidence && f.confidence < 70).length, 0);
      const unresolved = tender.documents.mentionedAttachments.filter(m => !m.resolved).length;
      tender.issues_count = lowConfidence + unresolved;
    }

    tenders[idx] = tender;
    saveStoredTenders(tenders);
    return tender;
  },

  /**
   * Deletes a tender.
   */
  deleteTender: async (tenderId: string): Promise<void> => {
    try {
      if (await isBackendReachable()) {
        await fetch(`${BACKEND_URL}/tenders/workspace/${tenderId}`, {
          method: "DELETE",
        });
      }
    } catch {
      // fall through
    }
    const tenders = getStoredTenders();
    const updated = tenders.filter((t) => t.id !== tenderId);
    saveStoredTenders(updated);
  }
};

/**
 * Downloads a file from a URL using fetch and validates its headers before saving as blob
 */
export async function handleSecureDownload(url: string, filename: string): Promise<void> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to download file. Server responded with status ${response.status}`);
  }
  
  const contentType = response.headers.get("content-type") || "";
  
  // Validation check: if filename is .xlsx, ensure content-type is excel-related and not JSON/HTML/Text
  if (filename.toLowerCase().endsWith(".xlsx")) {
    if (contentType.includes("json") || contentType.includes("html") || contentType.includes("text")) {
      throw new Error("Downloaded file is not a valid Excel spreadsheet (server returned text/json instead of workbook).");
    }
  }

  const blob = await response.blob();
  const blobUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = blobUrl;
  link.setAttribute("download", filename);
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(blobUrl);
}

