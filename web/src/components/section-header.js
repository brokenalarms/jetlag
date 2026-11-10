/**
 * Centred section header: pink pill label, scanlined h2, optional intro line.
 *
 * `introClass` sets the intro's width and tone (sections with shorter intros
 * use a narrower column); `className` sets the gap below the header.
 */
export function renderSectionHeader({
  label,
  title,
  intro = '',
  introClass = 'max-w-2xl text-base leading-relaxed text-white/55',
  className = 'mb-14',
}) {
  return /* html */`
    <div class="text-center ${className}">
      <span class="section-label">${label}</span>
      <h2 class="vhs-scanlines mt-5 text-3xl font-bold tracking-tight sm:text-4xl">
        ${title}
      </h2>
      ${intro ? /* html */`<p class="mt-4 mx-auto ${introClass}">${intro}</p>` : ''}
    </div>
  `
}
