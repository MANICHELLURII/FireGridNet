export default function ComingSoon({ title }) {
  return (
    <section className="coming-soon panel">
      <div className="coming-soon-mark" aria-hidden="true">✦</div>
      <h2>{title}</h2>
      <p>This section is coming soon.</p>
    </section>
  );
}
