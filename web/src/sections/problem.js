export function renderProblem() {
  return /* html */`
    <section class="py-24 px-6">
      <div class="mx-auto max-w-5xl">
        <div class="grid gap-12 lg:grid-cols-2 lg:items-center">
          <!-- Text side -->
          <div>
            <span class="section-label">The Problem</span>
            <h2 class="mt-5 text-3xl font-bold tracking-tight sm:text-4xl">
              Cameras lie about time
            </h2>
            <p class="mt-4 text-base leading-relaxed text-white/55">
              GoPro stores timestamps in FAT filesystem time — no timezone info. Your iPhone records in UTC.
              Your drone adds a different offset. By the time you import to Final Cut Pro, every clip is
              hours apart in the timeline, even though they were all rolling at the same moment.
            </p>
            <p class="mt-4 text-base leading-relaxed text-white/55">
              You end up manually dragging clips around for hours, second-guessing every cut.
            </p>
          </div>

          <!-- Visual side — before/after timeline -->
          <div class="space-y-4">
            <div class="card">
              <div class="mb-3 flex items-center gap-2">
                <div class="h-2 w-2 rounded-full bg-red-400"></div>
                <span class="text-xs font-semibold uppercase tracking-widest text-red-400/80">Before Jetlag</span>
              </div>
              <div class="space-y-2">
                <div class="flex items-center gap-3">
                  <span class="w-20 text-right text-xs text-white/30 font-mono">08:07</span>
                  <div class="h-7 rounded bg-blue-500/30 border border-blue-400/20 flex items-center px-3 text-xs text-blue-300/70" style="width: 140px">GH012345.MP4</div>
                </div>
                <div class="flex items-center gap-3">
                  <span class="w-20 text-right text-xs text-white/30 font-mono">15:09</span>
                  <div class="h-7 rounded bg-green-500/30 border border-green-400/20 flex items-center px-3 text-xs text-green-300/70" style="width: 100px; margin-left: 180px">IMG_0923.MOV</div>
                </div>
                <div class="flex items-center gap-3">
                  <span class="w-20 text-right text-xs text-white/30 font-mono">23:11</span>
                  <div class="h-7 rounded bg-purple-500/30 border border-purple-400/20 flex items-center px-3 text-xs text-purple-300/70" style="width: 90px; margin-left: 320px">DJI_0011.MP4</div>
                </div>
              </div>
              <p class="mt-3 text-xs text-white/30">Clips spread across 15 hours of phantom timeline</p>
            </div>

            <div class="card border-amber-500/20 bg-amber-500/5">
              <div class="mb-3 flex items-center gap-2">
                <div class="h-2 w-2 rounded-full bg-amber-400"></div>
                <span class="text-xs font-semibold uppercase tracking-widest text-amber-400/80">After Jetlag</span>
              </div>
              <div class="space-y-2">
                <div class="flex items-center gap-3">
                  <span class="w-20 text-right text-xs text-white/30 font-mono">08:07</span>
                  <div class="h-7 rounded bg-blue-500/30 border border-blue-400/20 flex items-center px-3 text-xs text-blue-300/70" style="width: 140px">GH012345.MP4</div>
                </div>
                <div class="flex items-center gap-3">
                  <span class="w-20 text-right text-xs text-white/30 font-mono">08:09</span>
                  <div class="h-7 rounded bg-green-500/30 border border-green-400/20 flex items-center px-3 text-xs text-green-300/70" style="width: 100px; margin-left: 14px">IMG_0923.MOV</div>
                </div>
                <div class="flex items-center gap-3">
                  <span class="w-20 text-right text-xs text-white/30 font-mono">08:11</span>
                  <div class="h-7 rounded bg-purple-500/30 border border-purple-400/20 flex items-center px-3 text-xs text-purple-300/70" style="width: 90px; margin-left: 28px">DJI_0011.MP4</div>
                </div>
              </div>
              <p class="mt-3 text-xs text-amber-400/60">All cameras aligned within seconds of each other</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  `
}
