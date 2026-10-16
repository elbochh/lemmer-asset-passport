# Lemmer Calgary service context
Source: Project-defined Calgary demo requirements; this file describes proposed demo behavior.
Status: Demo behavior implemented; branch reviewers's operational approval and real repair evidence are still pending.

Reception identifies the equipment owner separately from the person dropping it off. One customer can own several physical assets. Each physical asset has its own Asset ID, serial number and QR code. A repair visit has its own service request number. A catalogue product number is not the familiar model name or the physical asset's identity. SAP customer and sale document references are manually recorded; there is no live SAP connection.

Reception reviews scans, missing/uncertain extraction, operating condition, accessories, visible damage, customer instructions and assignment. Unknown values stay unknown. Technicians can receive an assigned request or see the unassigned queue. Existing open visits must be considered before creating another visit. Uploaded originals stay with the request and are staff-only until explicitly released to the owner.

Approved, equipment-applicable troubleshooting procedures are the first source for known problems. Their steps run as database rules with recorded answers; no language model is called per step. Similar wording is not a confirmed fault. The technician manually confirms diagnosis, actual work, parts and quantities, testing and outcome. Closure is a deliberate choice.

A completed report is permanent asset history. It does not train a model, browse the internet, or trigger a model call. A reusable procedure is a separate, versioned technical record with sources, applicability, human technical/privacy review and an approval decision. It must not copy private customer contacts, pricing or confidential notes into shared knowledge. Only approved procedures are shared for troubleshooting. AI evidence review is not Lemmer human approval.

the administrator's manufacturer role means the super-user who controls staff access and material corrections. There is no separate organization repair role. Individual and business owners use the customer role; reception assigns repairs to technicians. Named staff belong to Lemmer Calgary. Other locations are not part of this implementation.

Customers can report symptoms and request parts for their own equipment. Requests are enquiries to the branch, not stock, compatibility, price, warranty or delivery promises. There is no online payment. Maintenance intervals are observations or explicitly sourced estimates, never guaranteed component lifetime. Do not invent calibrated probabilities.

AI may match free wording to applicable approved procedure IDs, summarize cited evidence and ask questions. Technical support, customer privacy and communication quality are separate checks. Unsupported technical suggestions are withheld. Lack of a source must remain an explicit knowledge gap.

Actual technician experience, reception papers, troubleshooting procedures, repair outcomes, sign-off rules and evaluation holdouts have not been supplied. Do not invent employee qualifications, business policies or confirmed repairs. Synthetic fixtures are clearly labelled. The vehicle interface and later CV integration belong to the project partner and are outside this change.
