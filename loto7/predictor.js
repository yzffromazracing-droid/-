/*
 * ロト7 予想ロジック（ブラウザ / Node.js 共通）
 *
 * ロト7: 1〜37 から本数字7個 + ボーナス数字2個。
 * 抽選は毎回独立した無作為抽出なので、過去データから当選番号を
 * 「当てる」ことはできない。ここでは過去の傾向を重み付けに使って
 * 買い目を組み立て、バックテストでその効果を検証できるようにしている。
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.Loto7 = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const MAX = 37;
  const PICK = 7;
  const BONUS = 2;

  /**
   * 1行から日付・金額を取り除き、区切り文字で分けた「数字だけのトークン」を取り出す。
   * 「本数字1」「B1」「2口」のように文字が付いたものは数字として扱わない。
   */
  function tokenize(line) {
    const cleaned = line
      .replace(/\d{4}[\/\-.年]\d{1,2}[\/\-.月]\d{1,2}日?/g, " ")
      .replace(/\d{1,3}(,\d{3})+円?/g, " ");
    return cleaned
      .split(/[\s,;|()（）\[\]、・:]+/)
      .filter((t) => /^\d+$/.test(t))
      .map(Number);
  }

  function validMain(nums) {
    return nums.length === PICK && new Set(nums).size === PICK && nums.every((n) => n >= 1 && n <= MAX);
  }

  /**
   * 過去の当選番号テキスト（CSV・タブ区切り・サイトの表のコピペなど）を解析する。
   * 各行で「1〜37の重複しない7個の連続した数字」を本数字とみなし、
   * その直前の数字を回号、直後の2個をボーナス数字として扱う。
   * 回号があれば回号の昇順（古い順）に並べ替える。
   */
  function parseResults(text) {
    const draws = [];
    const seen = new Set();
    for (const line of String(text).split(/\r?\n/)) {
      const labeled = line.match(/第\s*(\d+)\s*回/);
      const tokens = tokenize(labeled ? line.replace(labeled[0], " ") : line);
      // 8個・10個なら先頭は回号（回号が37以下でも本数字と取り違えないように）
      const start = !labeled && (tokens.length === PICK + 1 || tokens.length === PICK + BONUS + 1) ? 1 : 0;
      for (let i = start; i + PICK <= tokens.length; i++) {
        const main = tokens.slice(i, i + PICK);
        if (!validMain(main)) continue;
        let no = labeled ? Number(labeled[1]) : i > 0 ? tokens[i - 1] : null;
        const rest = tokens.slice(i + PICK, i + PICK + BONUS);
        const bonus =
          rest.length === BONUS &&
          new Set(rest).size === BONUS &&
          rest.every((n) => n >= 1 && n <= MAX && !main.includes(n))
            ? rest
            : [];
        const key = no != null ? "#" + no : main.slice().sort((a, b) => a - b).join(",");
        if (no != null && seen.has(key)) break;
        seen.add(key);
        draws.push({ no, main: main.slice().sort((a, b) => a - b), bonus });
        break;
      }
    }
    if (draws.length && draws.every((d) => d.no != null)) {
      draws.sort((a, b) => a.no - b.no);
    }
    return draws;
  }

  /** 各数字の統計 */
  function computeStats(draws, recentWindow) {
    const window = Math.min(recentWindow || 50, draws.length);
    const total = new Array(MAX + 1).fill(0);
    const recent = new Array(MAX + 1).fill(0);
    const gap = new Array(MAX + 1).fill(draws.length);
    draws.forEach((d, idx) => {
      for (const n of d.main) {
        total[n]++;
        if (idx >= draws.length - window) recent[n]++;
        gap[n] = draws.length - 1 - idx;
      }
    });
    const sums = draws.map((d) => d.main.reduce((a, b) => a + b, 0)).sort((a, b) => a - b);
    const pct = (p) => (sums.length ? sums[Math.min(sums.length - 1, Math.floor(p * sums.length))] : 0);
    const numbers = [];
    for (let n = 1; n <= MAX; n++) {
      numbers.push({ n, total: total[n], recent: recent[n], gap: gap[n] });
    }
    return {
      draws: draws.length,
      window,
      numbers,
      expectedPerDraw: PICK / MAX,
      sumRange: [pct(0.1), pct(0.9)],
    };
  }

  /** 戦略ごとの各数字の重み（index 1..37） */
  function weightsFor(strategy, stats) {
    const w = new Array(MAX + 1).fill(0);
    const maxRecent = Math.max(1, ...stats.numbers.map((x) => x.recent));
    const maxGap = Math.max(1, ...stats.numbers.map((x) => x.gap));
    for (const x of stats.numbers) {
      const hot = (x.recent + 1) / (maxRecent + 1);
      const cold = (x.gap + 1) / (maxGap + 1);
      switch (strategy) {
        case "hot":
          w[x.n] = hot;
          break;
        case "cold":
          w[x.n] = cold;
          break;
        case "mixed":
          w[x.n] = (hot + cold) / 2;
          break;
        default:
          w[x.n] = 1;
      }
    }
    return w;
  }

  /** 再現可能な乱数（mulberry32） */
  function seededRandom(seed) {
    let a = seed >>> 0;
    return function () {
      a = (a + 0x6d2b79f5) >>> 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function weightedPick(weights, rng) {
    const pool = [];
    for (let n = 1; n <= MAX; n++) pool.push(n);
    const picked = [];
    while (picked.length < PICK) {
      const sum = pool.reduce((s, n) => s + weights[n], 0);
      let r = rng() * sum;
      let idx = pool.length - 1;
      for (let i = 0; i < pool.length; i++) {
        r -= weights[pool[i]];
        if (r < 0) {
          idx = i;
          break;
        }
      }
      picked.push(pool.splice(idx, 1)[0]);
    }
    return picked.sort((a, b) => a - b);
  }

  /** 合計値が過去の中央80%に収まり、奇数が2〜5個の組み合わせか */
  function isBalanced(set, stats) {
    const sum = set.reduce((a, b) => a + b, 0);
    const odd = set.filter((n) => n % 2).length;
    const [lo, hi] = stats.sumRange;
    const sumOk = stats.draws < 10 || (sum >= lo && sum <= hi);
    return sumOk && odd >= 2 && odd <= 5;
  }

  /**
   * 買い目を生成する。
   * options: { strategy: "hot"|"cold"|"mixed"|"random", count, balance, window, rng }
   */
  function predict(draws, options) {
    const opts = Object.assign({ strategy: "mixed", count: 5, balance: true, window: 50 }, options);
    const rng = opts.rng || Math.random;
    const stats = computeStats(draws, opts.window);
    const weights = weightsFor(opts.strategy, stats);
    const sets = [];
    const keys = new Set();
    for (let tries = 0; sets.length < opts.count && tries < opts.count * 200; tries++) {
      const set = weightedPick(weights, rng);
      const key = set.join(",");
      if (keys.has(key)) continue;
      if (opts.balance && tries < opts.count * 150 && !isBalanced(set, stats)) continue;
      keys.add(key);
      sets.push(set);
    }
    return sets;
  }

  /**
   * バックテスト: 各回について、それより前のデータだけで買い目を作り、
   * 実際の本数字といくつ一致したかを集計する。
   */
  function backtest(draws, options) {
    const opts = Object.assign({ strategy: "mixed", tickets: 5, minHistory: 50, balance: true, window: 50, seed: 1 }, options);
    const rng = seededRandom(opts.seed);
    const hitCounts = new Array(PICK + 1).fill(0);
    let tickets = 0;
    let hits = 0;
    for (let i = opts.minHistory; i < draws.length; i++) {
      const history = draws.slice(0, i);
      const actual = new Set(draws[i].main);
      const sets = predict(history, {
        strategy: opts.strategy,
        count: opts.tickets,
        balance: opts.balance,
        window: opts.window,
        rng,
      });
      for (const set of sets) {
        const h = set.filter((n) => actual.has(n)).length;
        hitCounts[h]++;
        hits += h;
        tickets++;
      }
    }
    return {
      strategy: opts.strategy,
      tickets,
      averageHits: tickets ? hits / tickets : 0,
      expectedRandom: (PICK * PICK) / MAX,
      hitCounts,
    };
  }

  return {
    MAX,
    PICK,
    BONUS,
    parseResults,
    computeStats,
    predict,
    backtest,
    seededRandom,
    isBalanced,
  };
});
