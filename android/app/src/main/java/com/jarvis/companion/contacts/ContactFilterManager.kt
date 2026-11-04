package com.jarvis.companion.contacts

import android.content.Context
import android.util.Log
import org.json.JSONObject

/**
 * Manages which contacts Jarvis is allowed to pick up calls for.
 *
 * FilterMode.ALL_SAVED  → Jarvis picks up calls from ALL saved contacts (default)
 * FilterMode.CUSTOM     → Jarvis only picks up calls in the custom allow list
 *
 * Data stored in SharedPreferences("jarvis_contacts").
 */
class ContactFilterManager(private val context: Context) {

    private val tag = "ContactFilterManager"
    private val prefs = context.getSharedPreferences("jarvis_contacts", Context.MODE_PRIVATE)

    enum class FilterMode { ALL_SAVED, CUSTOM }

    // ------------------------------------------------------------------
    // Filter Mode
    // ------------------------------------------------------------------

    fun getFilterMode(): FilterMode {
        return when (prefs.getString("filter_mode", "ALL_SAVED")) {
            "CUSTOM" -> FilterMode.CUSTOM
            else -> FilterMode.ALL_SAVED
        }
    }

    fun setFilterMode(mode: FilterMode) {
        prefs.edit().putString("filter_mode", mode.name).apply()
        Log.i(tag, "Filter mode set to: $mode")
    }

    // ------------------------------------------------------------------
    // Custom Allow List (numbers Jarvis WILL pick up in CUSTOM mode)
    // ------------------------------------------------------------------

    fun getAllowedNumbers(): Set<String> {
        return prefs.getStringSet("allowed_numbers", emptySet()) ?: emptySet()
    }

    fun allowContact(phoneNumber: String) {
        val current = getAllowedNumbers().toMutableSet()
        val blocked = getBlockedNumbers().toMutableSet()
        current.add(normalizeNumber(phoneNumber))
        blocked.remove(normalizeNumber(phoneNumber))
        prefs.edit()
            .putStringSet("allowed_numbers", current)
            .putStringSet("blocked_numbers", blocked)
            .apply()
        Log.i(tag, "Contact ALLOWED: $phoneNumber")
    }

    // ------------------------------------------------------------------
    // Blocked Numbers (in ALL_SAVED mode, these are exceptions Jarvis won't pick)
    // ------------------------------------------------------------------

    fun getBlockedNumbers(): Set<String> {
        return prefs.getStringSet("blocked_numbers", emptySet()) ?: emptySet()
    }

    fun blockContact(phoneNumber: String) {
        val current = getBlockedNumbers().toMutableSet()
        val allowed = getAllowedNumbers().toMutableSet()
        current.add(normalizeNumber(phoneNumber))
        allowed.remove(normalizeNumber(phoneNumber))
        prefs.edit()
            .putStringSet("blocked_numbers", current)
            .putStringSet("allowed_numbers", allowed)
            .apply()
        Log.i(tag, "Contact BLOCKED: $phoneNumber")
    }

    // ------------------------------------------------------------------
    // Check if Jarvis should handle a specific number
    // ------------------------------------------------------------------

    fun shouldHandleCall(phoneNumber: String, allSavedContacts: Map<String, String>): Boolean {
        val norm = normalizeNumber(phoneNumber)
        val isSaved = allSavedContacts.keys.any { normalizeNumber(it) == norm }

        return when (getFilterMode()) {
            FilterMode.ALL_SAVED -> isSaved && !getBlockedNumbers().contains(norm)
            FilterMode.CUSTOM -> getAllowedNumbers().contains(norm)
        }
    }

    // ------------------------------------------------------------------
    // Build whitelist map to sync to cloud (number → name)
    // ------------------------------------------------------------------

    fun buildWhitelist(allSavedContacts: Map<String, String>): Map<String, String> {
        return when (getFilterMode()) {
            FilterMode.ALL_SAVED -> {
                val blocked = getBlockedNumbers()
                allSavedContacts.filter { (number, _) ->
                    !blocked.contains(normalizeNumber(number))
                }
            }
            FilterMode.CUSTOM -> {
                val allowed = getAllowedNumbers()
                allSavedContacts.filter { (number, _) ->
                    allowed.contains(normalizeNumber(number))
                }
            }
        }
    }

    // ------------------------------------------------------------------
    // Serialise whitelist to JSON for WebSocket transmission
    // ------------------------------------------------------------------

    fun buildWhitelistJson(allSavedContacts: Map<String, String>): JSONObject {
        val whitelist = buildWhitelist(allSavedContacts)
        val contactsJson = JSONObject()
        whitelist.forEach { (number, name) -> contactsJson.put(number, name) }
        return JSONObject().apply {
            put("type", "contacts_sync")
            put("contacts", contactsJson)
            put("filter_mode", getFilterMode().name)
            put("total", whitelist.size)
        }
    }

    // ------------------------------------------------------------------
    // Helper
    // ------------------------------------------------------------------

    private fun normalizeNumber(number: String): String {
        val cleaned = number.replace("[^+\\d]".toRegex(), "")
        // Normalize Indian numbers: add +91 prefix if 10 digits
        return when {
            cleaned.startsWith("+") -> cleaned
            cleaned.length == 10 -> "+91$cleaned"
            cleaned.length == 12 && cleaned.startsWith("91") -> "+$cleaned"
            else -> cleaned
        }
    }
}
