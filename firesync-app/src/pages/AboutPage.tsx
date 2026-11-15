import shared from '../styles/shared.module.css';
import styles from './AboutPage.module.css';

const HERO = {
    title: 'About FireSync',
    subtitle: 'Harmonizing satellite fire observations into a single consistent record.',
};

const ABOUT_SECTIONS = [
    {
        heading: 'What is FireSync?',
        body: 'FireSync is a research prototype for comparing MODIS and VIIRS active-fire detections. Explore and Compare display observations loaded into the local database. The default harmonized record is an identity baseline that retains matched MODIS FRP. A separate Bayesian preview demonstrates an exploratory fire-mask reconstruction. Its calibration is illustrative and its physical accuracy is unvalidated.',
    },
{
    heading: 'Why it matters',
    body: 'Wildfires and agricultural burns affect air quality, carbon budgets, biodiversity and human safety at continental scale. Satellites are the only practical way to monitor them globally, but the sensor gap has left fire analysts without a continuous, comparable record.',
},
];

const DATA_SOURCES = [
    {
        name: 'MODIS',
        fullName: 'Moderate Resolution Imaging Spectroradiometer',
        satellites: 'Terra (2000–) · Aqua (2002–)',
        period: '2003 – present',
        description:
        'NASA\'s Moderate Resolution Imaging Spectroradiometer (MODIS) instruments have provided more than two decades of global fire data. MODIS were the first family of remotely sensed fire data sets produced from a moderate resolution (~1 km), "fire-capable" sensors on-board terrestial satellites. In forest fire detection by remote sensing, a combination of the 4 µm and 11 µm bands is often used to separate the temperature change caused by the fire from the temperature in the background area.',
    },
{
    name: 'VIIRS',
    fullName: 'Visible Infrared Imaging Radiometer Suite',
    satellites: 'S-NPP (2012–) · NOAA-20 (2018–) · NOAA-21 (2023–) ',
    period: '2012 – present',
    description:
    'VIIRS improves on MODIS with a 375 m pixel size and a dedicated I4/I5 fire channel pair, allowing it to resolve smaller fires and reduce saturation at high intensity. It is the primary operational sensor for near-real-time fire monitoring.',
},
{
    name: 'Harmonized',
    fullName: 'Cross-sensor harmonized record',
    satellites: 'MODIS + VIIRS overlap period',
    period: 'Present',
    description:
    'As MODIS and VIIRS may reveal fire activity differently, their observations are not directly comparable. Wetherefore need a method that uses the observations without assuming that any individual measurement reveals the complete fire activity. The engineering record groups nearby detections and currently defaults to unchanged MODIS FRP. The separate Model Preview shows probabilistic grid reconstruction from fire masks and does not establish a common physical FRP scale. ',
},
];

const HOW_IT_WORKS = [
    {
        step: '01',
        title: 'Ingest',
        body: 'Raw CSV files are downloaded from the NASA FIRMS area API for each sensor, validated against the 30-field Phase 1 schema and stored in a DuckDB observations table. Each record receives a deterministic SHA-256 observation ID so reruns never create duplicates.',
    },
{
    step: '02',
    title: 'Overlap extraction',
    body: 'Only dates where both MODIS and VIIRS were operational are retained. Observations are filtered to the study region and stamped with a dataset version that changes whenever matching parameters change.',
},
{
    step: '03',
    title: 'Spatiotemporal matching',
    body: 'Each MODIS detection is paired with VIIRS detections within 30 minutes and within 1 km plus half the MODIS pixel footprint. A KD-tree makes the spatial search efficient at scale. Each VIIRS detection is assigned to at most one MODIS group (the closest one), and each MODIS group keeps at most 50 VIIRS detections.',
},
{
    step: '04',
    title: 'Bayesian harmonization',
    body: 'The independent C engine estimates a discrete latent fire field using exact inference on small problems or a particle smoother. The included mask preview uses illustrative parameters and exposes model-estimated fire probabilities. It does not supply a validated physical FRP retrieval or a forecasting accuracy claim.',
},
{
    step: '05',
    title: 'Analytics & delivery',
    body: 'The REST API serves downloaded detection counts and reported FRP totals from DuckDB. Missing coverage stays unknown. Seasonal anomalies require independently verified complete regional observation coverage and enough baseline years. The FireSync web application displays the harmonized record alongside the raw sensors so users can verify consistency.',
},
];

const TEAM: Array<{ name: string; role?: string; affiliation?: string }> = [];

const LINKS = [
    { label: 'NASA FIRMS', description: 'Fire Information for Resource Management System', url: 'https://firms.modaps.eosdis.nasa.gov' },
{ label: 'MODIS Active Fire', description: 'MODIS Collection 6.1 fire product documentation', url: 'https://modis-fire.umd.edu' },
{ label: 'VIIRS Active Fire', description: 'VIIRS 375 m active fire product', url: 'https://viirsland.gsfc.nasa.gov/Products/NASA/FireAndThermal.html' },
];

export function AboutPage() {
    return (
        <main className={shared.page}>
        <h1 className="visually-hidden">About FireSync</h1>

        <section className={styles.hero}>
        <h2 className={styles.heroTitle}>{HERO.title}</h2>
        <p className={styles.heroSubtitle}>{HERO.subtitle}</p>
        </section>

        {ABOUT_SECTIONS.map((s) => (
            <section key={s.heading} className={`${shared.card} ${styles.section}`}>
            <h2 className={styles.sectionHeading}>{s.heading}</h2>
            <p className={styles.sectionBody}>{s.body}</p>
            </section>
        ))}

        <section aria-labelledby="data-sources-heading" className={styles.section}>
        <h2 id="data-sources-heading" className={styles.sectionHeading}>Data sources</h2>
        <div className={styles.sourceGrid}>
        {DATA_SOURCES.map((src) => (
            <div key={src.name} className={`${shared.card} ${styles.sourceCard}`}>
            <h3 className={styles.sourceName}>{src.name}</h3>
            <p className={styles.sourceFullName}>{src.fullName}</p>
            <p className={styles.sourceSatellites}>{src.satellites}</p>
            <p className={styles.sourceBody}>{src.description}</p>
            </div>
        ))}
        </div>
        </section>

        <section aria-labelledby="how-it-works-heading" className={styles.section}>
        <h2 id="how-it-works-heading" className={styles.sectionHeading}>How it works</h2>
        <ol className={styles.stepList} role="list">
        {HOW_IT_WORKS.map((item) => (
            <li key={item.step} className={`${shared.card} ${styles.stepCard}`}>
            <span className={styles.stepNumber} aria-hidden="true">{item.step}</span>
            <div>
            <h3 className={styles.stepTitle}>{item.title}</h3>
            <p className={styles.stepBody}>{item.body}</p>
            </div>
            </li>
        ))}
        </ol>
        </section>

        {TEAM.length > 0 && (
            <section aria-labelledby="team-heading" className={styles.section}>
            <h2 id="team-heading" className={styles.sectionHeading}>Team</h2>
            <div className={styles.teamGrid}>
            {TEAM.map((member) => (
                <div key={member.name} className={`${shared.card} ${styles.teamCard}`}>
                <p className={styles.memberName}>{member.name}</p>
                {member.role && <p className={styles.memberRole}>{member.role}</p>}
                {member.affiliation && <p className={styles.memberAffiliation}>{member.affiliation}</p>}
                </div>
            ))}
            </div>
            </section>
        )}

        <section aria-labelledby="links-heading" className={styles.section}>
        <h2 id="links-heading" className={styles.sectionHeading}>Resources</h2>
        <ul className={styles.linkList} role="list">
        {LINKS.map((link) => (
            <li key={link.url}>
            <a
            href={link.url}
            className={styles.resourceLink}
            target="_blank"
            rel="noopener noreferrer"
            >
            <span className={styles.resourceLabel}>{link.label}</span>
            <span className={styles.resourceDescription}>{link.description}</span>
            </a>
            </li>
        ))}
        </ul>
        </section>
        </main>
    );
}
