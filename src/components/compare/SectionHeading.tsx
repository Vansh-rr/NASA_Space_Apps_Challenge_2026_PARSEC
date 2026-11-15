import styles from '../../pages/ComparePage.module.css';

interface Props {
  id: string;
  eyebrow: string;
  title: string;
  description: string;
}

export function SectionHeading({ id, eyebrow, title, description }: Props) {
  return (
    <div className={styles.heading}>
      <div>
        <p className={styles.eyebrow}>{eyebrow}</p>
        <h2 id={id} className={styles.headingTitle}>
          {title}
        </h2>
      </div>
      <p className={styles.headingDescription}>{description}</p>
    </div>
  );
}
