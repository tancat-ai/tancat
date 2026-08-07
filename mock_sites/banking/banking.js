/*
 * Account/session state for the banking mock (localStorage-backed,
 * deterministic, multi-user capable).
 *
 * Mirrors the interaction surface a real online-banking demo exposes:
 * a sign-in wall, an accounts dashboard with balances, per-account
 * transaction lists, an inter-account transfer form, and a bill-pay
 * form. State lives in localStorage so journeys that navigate between
 * pages keep a consistent session (the sign-in page redirects to the
 * dashboard once a session exists).
 *
 * Deterministic demo auth: any non-empty username/password signs in as
 * the demo customer (the mock is a local test target, not a real bank).
 * Balances are seeded on first visit and mutated by transfers/payments.
 */
(function () {
  "use strict";

  var SESSION_KEY = "mock_banking_session";
  var STATE_KEY = "mock_banking_state";
  var SEED = {
    user: "demo",
    accounts: [
      { id: "checking", name: "Checking Account", number: "4012888888881881", balance: 2450.0 },
      { id: "savings", name: "Savings Account", number: "6011111111111117", balance: 8900.0 },
    ],
    transactions: {
      checking: [
        { description: "Direct deposit - Acme Corp", amount: 2500.0, date: "2026-08-01" },
        { description: "Groceries - Market Fresh", amount: -86.42, date: "2026-07-29" },
        { description: "Coffee - Daily Grind", amount: -4.75, date: "2026-07-28" },
      ],
      savings: [
        { description: "Interest payment", amount: 12.5, date: "2026-07-31" },
        { description: "Transfer from checking", amount: 500.0, date: "2026-07-25" },
      ],
    },
  };

  function loadState() {
    try {
      var raw = localStorage.getItem(STATE_KEY);
      if (raw) {
        return JSON.parse(raw);
      }
    } catch (e) {
      /* fall through to seed */
    }
    return JSON.parse(JSON.stringify(SEED));
  }

  function saveState(state) {
    localStorage.setItem(STATE_KEY, JSON.stringify(state));
  }

  function getSession() {
    try {
      var raw = localStorage.getItem(SESSION_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  }

  window.MockBank = {
    /* ---- session / auth ---- */
    signIn: function (username) {
      localStorage.setItem(SESSION_KEY, JSON.stringify({ user: username }));
    },
    signOut: function () {
      localStorage.removeItem(SESSION_KEY);
    },
    isSignedIn: function () {
      return getSession() !== null;
    },
    currentUser: function () {
      var s = getSession();
      return s ? s.user : null;
    },
    /* Gated pages call this on load; redirects to the sign-in wall. */
    requireSignIn: function () {
      if (this.isSignedIn()) {
        return true;
      }
      window.location.replace("index.html");
      return false;
    },

    /* ---- accounts ---- */
    accounts: function () {
      return loadState().accounts;
    },
    accountById: function (id) {
      var state = loadState();
      for (var i = 0; i < state.accounts.length; i++) {
        if (state.accounts[i].id === id) {
          return state.accounts[i];
        }
      }
      return null;
    },
    transactionsFor: function (accountId) {
      return loadState().transactions[accountId] || [];
    },

    /* ---- transfers / payments (mutate balances deterministically) ---- */
    transfer: function (fromId, toId, amount) {
      var state = loadState();
      var from = null;
      var to = null;
      state.accounts.forEach(function (acc) {
        if (acc.id === fromId) {
          from = acc;
        }
        if (acc.id === toId) {
          to = acc;
        }
      });
      if (!from || !to) {
        return false;
      }
      from.balance -= amount;
      to.balance += amount;
      var today = new Date().toISOString().slice(0, 10);
      (state.transactions[fromId] = state.transactions[fromId] || []).unshift({
        description: "Transfer to " + to.name,
        amount: -amount,
        date: today,
      });
      (state.transactions[toId] = state.transactions[toId] || []).unshift({
        description: "Transfer from " + from.name,
        amount: amount,
        date: today,
      });
      saveState(state);
      return true;
    },
    payBill: function (payeeId, accountId, amount) {
      var state = loadState();
      var account = null;
      state.accounts.forEach(function (acc) {
        if (acc.id === accountId) {
          account = acc;
        }
      });
      if (!account) {
        return false;
      }
      account.balance -= amount;
      (state.transactions[accountId] = state.transactions[accountId] || []).unshift({
        description: "Bill payment - " + payeeId,
        amount: -amount,
        date: new Date().toISOString().slice(0, 10),
      });
      saveState(state);
      return true;
    },

    /* ---- test helpers ---- */
    reset: function () {
      localStorage.removeItem(SESSION_KEY);
      localStorage.removeItem(STATE_KEY);
    },
  };
})();
