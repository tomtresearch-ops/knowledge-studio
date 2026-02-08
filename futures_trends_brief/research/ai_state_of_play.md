# AI State of Play: Early 2026

**2026 Futures Report -- Foundation Brief**
**Compiled: February 7, 2026**

---

## Executive Summary

Artificial intelligence in early 2026 is defined by a paradox: capabilities are advancing at an unprecedented pace -- frontier models reason through multi-step problems, AI agents are deployed in production at over half of enterprises, and nearly $700 billion in capital expenditure is flowing into AI infrastructure this year alone -- yet persistent limitations in reliability, explainability, and real-world productivity gains remain stubbornly unresolved. The gap between what AI can demonstrate on benchmarks and what it consistently delivers in production is the central tension shaping the field.

---

## 1. Frontier LLM Capabilities

### The Model Landscape (as of February 2026)

Three families dominate the frontier:

| Model | Lab | Released | Key Strengths |
|-------|-----|----------|---------------|
| Claude Opus 4.6 | Anthropic | Feb 2026 | 1M token context, agentic coding, long-horizon tasks |
| Claude Opus 4.5 | Anthropic | Nov 2025 | Reasoning, math, coding efficiency |
| Claude Sonnet 4.5 | Anthropic | 2025 | Best coding model (SWE-bench 77.2%), computer use, agent building |
| GPT-5.2 | OpenAI | Dec 2025 | GPQA Diamond 93.2%, multimodal understanding |
| GPT-5 | OpenAI | Aug 2025 | AIME 2025 94.6% (no tools), SWE-bench 74.9% |
| Gemini 3 Pro | Google | Nov 2025 | First model to break 1500 LMArena Elo, Deep Think mode |
| DeepSeek-V3.2 | DeepSeek | Sep 2025 | Frontier-class at 10-30x lower cost |

### Benchmark State of the Art

- **Mathematical reasoning (AIME 2025):** 95% without tools; 100% with code execution
- **Expert knowledge (GPQA Diamond):** 93.2% (GPT-5.2 Pro)
- **Out-of-distribution reasoning (ARC-AGI-2):** 31.1% standard; 45.1% with Deep Think -- extremely high for this deliberately adversarial benchmark
- **Real-world coding (SWE-bench Verified):** ~75% for leading models (up from 33% in August 2024)
- **SWE-bench Pro (harder, long-horizon):** Claude Opus 4.5 leads at 45.89%, followed by Sonnet 4.5 at 43.60%
- **Multimodal understanding (MMMU):** 84.2% (GPT-5)
- **Long-context retrieval (MRCR v2, 1M tokens):** Claude Opus 4.6 scores 76% vs. Sonnet 4.5 at 18.5%
- **Humanity's Last Exam:** Claude Opus 4.6 leads all frontier models
- **Economic knowledge work (GDPval-AA):** Claude Opus 4.6 outperforms GPT-5.2 by ~144 Elo points

### What Changed in 2025

1. **Reasoning models became mainstream.** OpenAI's o1/o3 series, DeepSeek-R1, and Google's Deep Think mode proved that spending more compute at inference time -- "thinking longer" -- dramatically improves accuracy on hard problems.

2. **Context windows expanded to 1M tokens.** Claude Opus 4.6 operates effectively over 1 million tokens, enabling analysis of entire codebases, legal document sets, and research corpora in a single pass.

3. **The cost-performance frontier collapsed.** DeepSeek-V3 trained for ~$6 million (vs. ~$100M+ for GPT-4). API pricing dropped 100-200x below comparable proprietary models. GPT-4-level performance is now available at a fraction of 2023 costs.

4. **Deception rates declined measurably.** OpenAI reported reducing deception in model responses from 4.8% (o3) to 2.1% (GPT-5 reasoning).

5. **Multimodal became table stakes.** Every frontier model now handles text, images, code, and structured data natively.

---

## 2. AI Agents

### Production Deployment Status

AI agents have crossed the threshold from experimentation to production:

- **57% of companies** already have AI agents in production (G2, August 2025)
- **22%** are in pilot; **21%** in pre-pilot
- **Gartner forecasts 40%** of enterprise applications will embed AI agents by end of 2026, up from <5% in 2025
- **1,445% surge** in multi-agent system inquiries from Q1 2024 to Q2 2025 (Gartner)

### What Agents Can Do Now

- **Multi-step task completion:** Agents can reason in loops -- evaluate results, adjust strategies, and continue working toward objectives without per-step human prompting
- **Code generation and debugging:** GitHub Copilot has 1.3 million paid users across 50,000+ organizations; ~50% of all code on the platform is now AI-assisted
- **Computer use:** Google and Anthropic have released agents capable of controlling computers at near-human level, automating entire workflows through software interfaces
- **Research and analysis:** Agents can search, synthesize, and produce reports across multiple data sources, though quality varies
- **Multi-agent orchestration:** The most advanced deployments use teams of specialized agents coordinating on complex tasks

### Current Limitations

- **Reliability in novel situations:** Agents perform well on familiar task patterns but struggle with edge cases and novel environments
- **Oversight gap:** 78% of companies plan to increase agent autonomy in the next year, but 34% already use "let it rip" oversight where agents act first and humans review afterward
- **Security:** Most CISOs express deep concern about AI agent risks, yet only a handful have implemented mature safeguards. Organizations are deploying agents faster than they can secure them.
- **Benchmark vs. reality gap:** A METR randomized controlled trial found AI coding tools actually slow down experienced open-source developers, despite impressive benchmark scores -- highlighting the discrepancy between controlled evaluations and real-world productivity

### Market Scale

The AI agents market is valued at $12-15 billion in 2025, projected to reach $80-100 billion by 2030.

---

## 3. Enterprise Adoption

### Adoption Rates

- **78% of organizations** now use AI in at least one business function (up from 55% one year ago)
- Worker access to AI rose by **50% in 2025**
- **23%** of organizations are scaling agentic AI systems; **39%** are experimenting with AI agents
- The number of companies with 40%+ of AI projects in production is set to **double within six months**

### ROI Data

- **72% of enterprises** are formally measuring Gen AI ROI
- **Three out of four leaders** report positive returns on Gen AI investments
- Reported productivity gains: **26-55%** across implementations
- Average ROI: **$3.70 per dollar invested**
- ROI typically materializes within **12-24 months**
- **Four out of five** organizations see Gen AI investments paying off in 2-3 years

### Failure Rate

Despite positive topline metrics, **70-85% of AI projects still fail** -- a sobering counterpoint to adoption enthusiasm. **77% of businesses** worry about AI hallucinations affecting their operations.

### Job Displacement: The Numbers So Far

**Hard data:**
- **14% of all workers** report having already been displaced by AI, with higher rates among younger and mid-career workers in tech and creative fields
- **~55,000 job cuts** were directly attributed to AI in 2025 (out of 1.17 million total layoffs)
- An MIT study (November 2025) found AI can potentially replace **11.7% of the U.S. workforce**, though visible tech-sector layoffs represent only ~2.2% of total wage exposure

**Vulnerability patterns:**
- Workers aged 18-24 are **129% more likely** than those over 65 to worry AI will make their job obsolete
- Stanford (August 2025): Early-career workers (ages 22-25) in the most AI-exposed occupations experienced a **13% decline in employment** relative to less-exposed occupations
- **79% of employed women** in the U.S. work in jobs at high risk of automation (vs. 58% of men)

**Affected sectors:**
- Marketing consulting, graphic design, office administration, and telephone call centers have seen employment growth fall below trend
- However, HBR (January 2026) reports that companies are "laying off workers because of AI's potential -- not its performance," meaning many cuts are anticipatory rather than capability-driven

**Important context:** ITIF (December 2025) found that AI job gains currently outpace losses. The dramatic drop in graduate job postings appears driven primarily by economic uncertainty, post-COVID normalization, and accelerated offshoring rather than AI displacement alone.

---

## 4. AI Governance

### EU AI Act

- Early compliance deadlines are already in effect (prohibitions on unacceptable-risk AI since February 2025)
- The European Commission has **proposed extending** the applicability of high-risk AI rules from August 2, 2026, to **December 2027** at the latest
- These proposals aim to ease compliance burdens by giving providers of general-purpose AI models additional time to update documentation and processes
- Broader obligations for general-purpose AI models are phasing in throughout 2025-2026

### United States

- **December 11, 2025:** President Trump signed Executive Order 14365, "Ensuring a National Policy Framework for Artificial Intelligence"
- The EO establishes a federal policy aimed at "sustaining and enhancing the United States' global AI dominance through a minimally burdensome national policy framework"
- The DOJ is mobilized to identify and challenge "onerous" state AI laws
- Federal broadband funding is conditioned on policy alignment with federal AI approach
- **Carve-outs:** Child safety, AI computing infrastructure, state government procurement
- **State-level activity:** California's Transparency in Frontier AI Act and Texas's Responsible AI Governance Act took effect January 1, 2026. Colorado's AI Act goes into effect June 30, 2026.

### China

- China's top legislature **amended the Cybersecurity Law** (October 28, 2025) to include AI provisions for the first time, effective January 1, 2026
- The **State Council issued the "AI Plus Action Plan"** (August 2025) -- the blueprint for national AI strategy targeting **70% AI penetration in key sectors by 2027** and **90% by 2030**
- China is prioritizing pilots, standards, and targeted rules while keeping compliance costs low
- The **AI Governance Framework** (September 2025) outlines principles for governance and risk management
- **30+ new standards** relating to public data, data infrastructure, and AI agents are expected in 2026
- Overall approach: Balance technological innovation with data security, privacy protection, and IP rights

### The Governance Gap

The EU, US, UK, and China are pursuing **sharply different regulatory approaches**, increasing cross-border complexity. The US favors minimal federal regulation and preemption of state laws. The EU is building comprehensive risk-based frameworks but delaying enforcement timelines. China is promoting rapid deployment while embedding AI into national law. The UK maintains a principles-based, sector-specific approach.

**Critical tension:** Regulation is trailing capability by 2-3 years minimum. Agentic AI systems operating across enterprise boundaries, making autonomous decisions with financial and legal consequences, currently operate in a regulatory vacuum in most jurisdictions.

---

## 5. Scaling Laws

### Are They Holding?

The answer is nuanced: **traditional pre-training scaling laws are slowing, but new scaling dimensions have opened.**

**Pre-training scaling:** Inside labs, the consensus is growing that simply adding more data and compute will not create transformative AI alone. The binding constraint is frequently availability of power and transmission capacity, not just the price of compute.

**However, three scaling axes are now active simultaneously:**

1. **Pre-training scale** (the original Chinchilla/Kaplan paradigm): Still delivering gains, but with diminishing returns per dollar on the frontier
2. **Inference-time compute** (test-time compute / reasoning): The breakout scaling axis of 2024-2025. OpenAI's o1 proved that spending more compute at generation time via deliberation and search dramatically raises problem-solving performance. This is a largely unexplored frontier with enormous headroom.
3. **Architecture efficiency** (Mixture of Experts, multi-head latent attention, sliding window attention, linear attention): Making the same compute go further. DeepSeek demonstrated that architectural innovation can deliver frontier performance at a fraction of the cost.

### Cost-Aware Scaling

Research extending the Chinchilla framework now incorporates inference costs into compute-optimal scaling. Key insight: in high-usage settings, **smaller models trained on more data can match larger models while incurring lower total compute costs.**

### The Densing Law

Published in Nature Machine Intelligence, the "Densing Law" formalizes the observation that model efficiency is improving at a predictable rate -- GPT-4-level performance is achievable at dramatically lower cost each year.

### Infrastructure Reality

- Big tech capex is approaching **$700 billion in 2026** (Alphabet, Amazon, Meta, Microsoft combined)
- The Stargate initiative targets **$500 billion** for up to 10 data centers (each potentially requiring 5 GW)
- Power availability, not chip supply, is becoming the binding constraint

---

## 6. Key Milestones of 2025

### Model Releases and Capability Jumps

1. **DeepSeek R1 (January 2025):** Open-source reasoning model matching or exceeding proprietary models at 100-200x lower API cost. Training cost: ~$6 million. Sent shockwaves through global markets and forced a reassessment of the cost of frontier AI.

2. **Gemini 2.5 (March 2025) and Gemini 3 Pro (November 2025):** Google's models achieved the first 1500+ LMArena Elo score. Gemini 3 introduced "Deep Think" mode enabling 10-15 step coherent reasoning chains.

3. **GPT-5 (August 2025):** OpenAI's most capable system, setting SOTA across math, coding, multimodal understanding, and health benchmarks. Followed by GPT-5.1 (November) and GPT-5.2 (December).

4. **Claude Sonnet 4.5 and Opus 4.5 (2025):** Anthropic established state-of-the-art in real-world coding (SWE-bench), computer use, and agent construction.

5. **DeepSeek-V3.1 and V3.2 (September 2025):** Continued the open-source efficiency revolution with improved context handling and safety alignment.

### AI Proves Itself in Formal Domains

- Reasoning models from Google DeepMind and OpenAI **won gold at the International Math Olympiad** and derived new mathematical results
- Google DeepMind announced Gemini Pro reasoning helped speed up the training of Gemini Pro itself -- AI improving AI

### Hardware and Infrastructure

- **Google TPU v6 (March 2025):** 30% better energy efficiency, superior scalability for massive model training
- **Quantum-AI convergence:** IBM's 120-qubit "Nighthawk" processor won pilot quantum advantage in ML tasks (34% accuracy improvement for a trading model). Google's 105-qubit "Echoes" algorithm ran 13,000x faster than a classical supercomputer on a physics simulation.

### Enterprise Deployment Milestones

- GitHub Copilot reached **1.3 million paid users** across **50,000+ organizations**
- **~50%** of all code on GitHub now AI-assisted
- Banks and insurers deployed LLMs fine-tuned for domain-specific reasoning in full-scale production

### Open-Source Momentum

- China emerged as the leader in open-source AI models by end of 2025
- Chinese firms distributed top-tier models for free, reshaping the competitive landscape
- The gap between open-source and proprietary models narrowed significantly

### Investment Scale

- **$202.3 billion** invested in the AI sector in 2025
- Foundation model companies raised **$80 billion** (40% of global AI funding)
- Big tech aggregate capex: **~$427 billion in 2025**, projected **~$650-700 billion in 2026**

---

## 7. Current Limitations

### What AI Cannot Do (Yet)

**1. Reliably tell truth from fabrication**
- Hallucination remains unsolved. AI generates confident but false information at rates that vary by domain and prompt complexity.
- Real-world example: Dozens of papers accepted at NeurIPS 2025 contained AI-generated citations that were not caught during peer review, with hundreds of flawed references across at least 50 papers.
- While deception rates are declining (OpenAI reported reducing from 4.8% to 2.1%), they remain too high for autonomous deployment in high-stakes domains.

**2. Produce genuine scientific insight**
- Most experts agree that failure to generate original insights of scientific value remains a major shortcoming. AI agents tasked with producing scientific papers generally recycle existing ideas or pursue tangential, uninteresting hypotheses.

**3. Learn and remember across sessions**
- Current systems cannot retain information across sessions. Resolving this limitation will require at least one meaningful breakthrough. Every conversation starts from zero (absent external memory systems).

**4. Consistently improve real-world productivity**
- Despite impressive benchmarks, a METR randomized controlled trial found AI coding tools actually slowed down experienced open-source developers. The gap between controlled evaluations and messy real-world use remains significant.

**5. Explain its reasoning transparently**
- AI models produce results without clear explanation of underlying logic. This reduces trust in healthcare, law, finance, and other high-stakes applications.

**6. Operate without massive energy consumption**
- U.S. data centers consumed **183 TWh** in 2024 (4%+ of national electricity)
- Projected to reach **426 TWh by 2030** (133% growth)
- AI data centers alone expected to consume **90 TWh annually by 2026** (~10x 2022 levels)
- Carbon footprint: **32.6-79.7 million tons of CO2** in 2025
- Water footprint: **312.5-764.6 billion liters** in 2025
- The Stargate initiative alone could require **50 GW** of power capacity

**7. Navigate ambiguity and context the way humans do**
- AI misses tone, fails to adapt to genuinely novel situations, and often misreads casual language. This limits deployment in roles requiring social intelligence, negotiation, or nuanced judgment.

**8. Scale inference without proportional cost**
- Reasoning models ("thinking longer") dramatically improve accuracy, but at proportionally higher inference costs. The best performance on hard problems requires 2-10x more compute per query.

**9. Operate autonomously with consistent safety**
- 34% of companies already use "let it rip" oversight for AI agents. Security frameworks have not kept pace with deployment speed. Most CISOs lack mature safeguards for autonomous AI systems.

**10. Handle real-world data quality**
- Data quality has become the top challenge for successful GenAI adoption. Poor, incomplete, or biased training data leads to inaccurate responses, compliance violations, and security vulnerabilities.

---

## Key Tensions Shaping 2026

| Tension | Current State |
|---------|--------------|
| Capability vs. Reliability | Models ace benchmarks but hallucinate in production |
| Deployment Speed vs. Governance | 57% of companies have agents in production; regulation is 2-3 years behind |
| Investment vs. ROI | ~$700B in 2026 capex; 70-85% of AI projects still fail |
| Benchmark Gains vs. Productivity Gains | SWE-bench scores doubled; experienced developers aren't faster |
| Open-Source vs. Proprietary | DeepSeek matches frontier models at 1/100th the cost |
| Energy Demand vs. Sustainability | AI power consumption growing 10x; power availability is the binding constraint |
| Job Creation vs. Job Displacement | Gains currently outpace losses, but early-career workers already feel the impact |
| US vs. China Competition | US leads in frontier models; China leads in open-source and cost efficiency |

---

## Sources

### LLM Capabilities and Benchmarks
- [LM Council AI Benchmarks Feb 2026](https://lmcouncil.ai/benchmarks)
- [Vellum Flagship Model Report: GPT-5.1 vs Gemini 3 Pro vs Claude Opus 4.5](https://www.vellum.ai/blog/flagship-model-report)
- [Klu 2026 LLM Leaderboard](https://klu.ai/llm-leaderboard)
- [Atoms.dev 2025 LLM Review](https://atoms.dev/blog/2025-llm-review-gpt-5-2-gemini-3-pro-claude-4-5)
- [OpenAI: Introducing GPT-5](https://openai.com/index/introducing-gpt-5/)
- [OpenAI: GPT-5.1](https://openai.com/index/gpt-5-1/)
- [OpenAI: Introducing GPT-5.2](https://openai.com/index/introducing-gpt-5-2/)
- [Anthropic: Introducing Claude Opus 4.5](https://www.anthropic.com/news/claude-opus-4-5)
- [Anthropic: Introducing Claude Opus 4.6](https://www.anthropic.com/news/claude-opus-4-6)
- [Anthropic: Introducing Claude Sonnet 4.5](https://www.anthropic.com/news/claude-sonnet-4-5)
- [Anthropic: Introducing Claude 4](https://www.anthropic.com/news/claude-4)

### AI Agents
- [G2 Enterprise AI Agents Report](https://learn.g2.com/enterprise-ai-agents-report)
- [IBM: AI Tech Trends 2026](https://www.ibm.com/think/news/ai-tech-trends-predictions-2026)
- [Machine Learning Mastery: 7 Agentic AI Trends](https://machinelearningmastery.com/7-agentic-ai-trends-to-watch-in-2026/)
- [CIO: Taming AI Agents](https://www.cio.com/article/4064998/taming-ai-agents-the-autonomous-workforce-of-2026.html)
- [Blue Prism: Future of AI Agents](https://www.blueprism.com/resources/blog/future-ai-agents-trends/)

### Enterprise Adoption and ROI
- [Deloitte: State of AI in the Enterprise 2026](https://www.deloitte.com/us/en/what-we-do/capabilities/applied-artificial-intelligence/content/state-of-ai-in-the-enterprise.html)
- [McKinsey: The State of AI in 2025](https://www.mckinsey.com/capabilities/quantumblack/our-insights/the-state-of-ai)
- [Wharton: 2025 AI Adoption Report](https://knowledge.wharton.upenn.edu/special-report/2025-ai-adoption-report/)
- [Menlo Ventures: State of GenAI in the Enterprise](https://menlovc.com/perspective/2025-the-state-of-generative-ai-in-the-enterprise/)
- [ISG: Enterprise AI Adoption Report 2025](https://isg-one.com/state-of-enterprise-ai-adoption-report-2025)

### Job Displacement
- [Yale Budget Lab: AI Impact on Labor Market](https://budgetlab.yale.edu/research/evaluating-impact-ai-labor-market-current-state-affairs)
- [CNBC: MIT Study on AI Workforce Replacement](https://www.cnbc.com/2025/11/26/mit-study-finds-ai-can-already-replace-11point7percent-of-us-workforce.html)
- [HBR: Companies Laying Off Workers Because of AI's Potential](https://hbr.org/2026/01/companies-are-laying-off-workers-because-of-ais-potential-not-its-performance)
- [ITIF: AI's Job Impact](https://itif.org/publications/2025/12/18/ais-job-impact-gains-outpace-losses/)
- [Brookings: Workers' Capacity to Adapt to AI Displacement](https://www.brookings.edu/articles/measuring-us-workers-capacity-to-adapt-to-ai-driven-job-displacement/)
- [Goldman Sachs: AI and the Global Workforce](https://www.goldmansachs.com/insights/articles/how-will-ai-affect-the-global-workforce)

### AI Governance
- [White House: EO on National AI Policy Framework (Dec 2025)](https://www.whitehouse.gov/presidential-actions/2025/12/eliminating-state-law-obstruction-of-national-artificial-intelligence-policy/)
- [Gunderson Dettmer: 2026 AI Laws Update](https://www.gunder.com/en/news-insights/insights/2026-ai-laws-update-key-regulations-and-practical-guidance)
- [Holistic AI: AI Regulation in 2026](https://www.holisticai.com/blog/ai-regulation-in-2026-navigating-an-uncertain-landscape)
- [Wilson Sonsini: 2026 AI Regulatory Developments](https://www.wsgr.com/en/insights/2026-year-in-preview-ai-regulatory-developments-for-companies-to-watch-out-for.html)
- [IAPP: China AI Governance](https://iapp.org/resources/article/global-ai-governance-china)
- [East Asia Forum: China AI Governance Reset](https://eastasiaforum.org/2025/12/25/china-resets-the-path-to-comprehensive-ai-governance/)
- [Mayer Brown: China AI Global Governance Action Plan](https://www.mayerbrown.com/en/insights/publications/2025/10/artificial-intelligence-a-brave-new-world-china-formulates-new-ai-global--governance-action-plan-and-issues-draft-ethics-rules-and-ai-labelling-rules)

### Scaling Laws
- [Semi Analysis: Scaling Laws, o1 Pro Architecture](https://newsletter.semianalysis.com/p/scaling-laws-o1-pro-architecture-reasoning-training-infrastructure-orion-and-claude-3-5-opus-failures)
- [AI Multiple: LLM Scaling Laws 2026](https://research.aimultiple.com/llm-scaling-laws/)
- [Four Week MBA: Three Scaling Laws Drive Intelligence Forward](https://fourweekmba.com/ai-trend-2026-three-scaling-laws-drive-intelligence-forward/)
- [Lex Fridman Podcast #490: State of AI in 2026](https://lexfridman.com/ai-sota-2026-transcript/)
- [Nature Machine Intelligence: Densing Law of LLMs](https://www.nature.com/articles/s42256-025-01137-0)

### Milestones, Limitations, and Energy
- [KDnuggets: 10 AI Developments That Defined 2025](https://www.kdnuggets.com/the-10-ai-developments-that-defined-2025)
- [TIME: 5 AI Developments That Reshaped 2025](https://time.com/7341939/ai-developments-2025-trump-china/)
- [Google: 2025 Research Breakthroughs](https://blog.google/innovation-and-ai/products/2025-research-breakthroughs/)
- [MIT Technology Review: AI Coding Everywhere](https://www.technologyreview.com/2025/12/15/1128352/rise-of-ai-coding-developers-2026/)
- [METR: AI Impact on Developer Productivity](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/)
- [UK AISI: Mapping Limitations of Current AI](https://www.aisi.gov.uk/blog/mapping-the-limitations-of-current-ai-systems)
- [IEA: Energy Demand from AI](https://www.iea.org/reports/energy-and-ai/energy-demand-from-ai)
- [Pew Research: Data Center Energy Use](https://www.pewresearch.org/short-reads/2025/10/24/what-we-know-about-energy-use-at-us-data-centers-amid-the-ai-boom/)
- [Carbon Brief: AI Data Centre Energy in Context](https://www.carbonbrief.org/ai-five-charts-that-put-data-centre-energy-use-and-emissions-into-context/)

### Investment
- [Goldman Sachs: Why AI Companies May Invest $500B+ in 2026](https://www.goldmansachs.com/insights/articles/why-ai-companies-may-invest-more-than-500-billion-in-2026)
- [CNBC: Tech AI Spending Approaches $700B in 2026](https://www.cnbc.com/2026/02/06/google-microsoft-meta-amazon-ai-cash.html)
- [Crunchbase: Big AI Funding Trends of 2025](https://news.crunchbase.com/ai/big-funding-trends-charts-eoy-2025/)
- [Yahoo Finance: Big Tech $650B AI Capex in 2026](https://finance.yahoo.com/news/big-tech-set-to-spend-650-billion-in-2026-as-ai-investments-soar-163907630.html)

### DeepSeek
- [DeepSeek: R1 Release](https://api-docs.deepseek.com/news/news250120)
- [World Economic Forum: Open-Source AI and DeepSeek](https://www.weforum.org/stories/2025/02/open-source-ai-innovation-deepseek/)
- [CNBC: DeepSeek Upgraded R1](https://www.cnbc.com/2025/05/29/chinas-deepseek-releases-upgraded-r1-ai-model-in-openai-competition.html)

---

*This document serves as the factual foundation for the 2026 Futures Report AI domain predictions. All statistics and claims are sourced from the references listed above. Data is current as of February 7, 2026.*
