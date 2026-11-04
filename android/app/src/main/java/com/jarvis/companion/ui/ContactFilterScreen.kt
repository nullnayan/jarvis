package com.jarvis.companion.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.jarvis.companion.automation.PhoneAutomator
import com.jarvis.companion.contacts.ContactFilterManager
import com.jarvis.companion.contacts.ContactFilterManager.FilterMode

data class ContactItem(
    val name: String,
    val number: String,
    var isAllowed: Boolean,
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ContactFilterScreen(
    onBack: () -> Unit,
    onSyncContacts: (Map<String, String>) -> Unit,
) {
    val context = LocalContext.current
    val filterManager = remember { ContactFilterManager(context) }
    val phoneAutomator = remember { PhoneAutomator(context) }

    var filterMode by remember { mutableStateOf(filterManager.getFilterMode()) }
    var searchQuery by remember { mutableStateOf("") }
    var contacts by remember { mutableStateOf<List<ContactItem>>(emptyList()) }
    var isSyncing by remember { mutableStateOf(false) }
    var syncMessage by remember { mutableStateOf("") }
    var showModeDropdown by remember { mutableStateOf(false) }

    // Load contacts on first composition
    LaunchedEffect(Unit) {
        val savedContacts = phoneAutomator.getSavedContacts()
        val allowedNums = filterManager.getAllowedNumbers()
        val blockedNums = filterManager.getBlockedNumbers()
        contacts = savedContacts.entries
            .map { (number, name) ->
                val normNumber = number.replace("[^+\\d]".toRegex(), "")
                val isAllowed = when (filterMode) {
                    FilterMode.ALL_SAVED -> !blockedNums.contains(normNumber)
                    FilterMode.CUSTOM -> allowedNums.contains(normNumber)
                }
                ContactItem(name = name, number = normNumber, isAllowed = isAllowed)
            }
            .sortedBy { it.name }
    }

    val filteredContacts = remember(contacts, searchQuery) {
        if (searchQuery.isBlank()) contacts
        else contacts.filter {
            it.name.contains(searchQuery, ignoreCase = true) ||
                    it.number.contains(searchQuery)
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("🛡️ Call Filter", fontWeight = FontWeight.Bold, fontSize = 18.sp)
                        Text(
                            "Choose who Jarvis answers for",
                            fontSize = 12.sp,
                            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
                        )
                    }
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = Color(0xFF0A0A1A),
                    titleContentColor = Color.White,
                    navigationIconContentColor = Color.White,
                ),
            )
        },
        containerColor = Color(0xFF0A0A1A),
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp),
        ) {
            Spacer(Modifier.height(12.dp))

            // --- Filter Mode Selector ---
            Box {
                OutlinedCard(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { showModeDropdown = true },
                    shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.outlinedCardColors(
                        containerColor = Color(0xFF12122A),
                    ),
                ) {
                    Row(
                        modifier = Modifier.padding(16.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(
                            if (filterMode == FilterMode.ALL_SAVED) Icons.Default.People else Icons.Default.FilterList,
                            contentDescription = null,
                            tint = Color(0xFF6C63FF),
                        )
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Text(
                                "Filter Mode",
                                fontSize = 12.sp,
                                color = Color.Gray,
                            )
                            Text(
                                if (filterMode == FilterMode.ALL_SAVED) "All Saved Contacts" else "Custom List Only",
                                color = Color.White,
                                fontWeight = FontWeight.SemiBold,
                            )
                        }
                        Icon(Icons.Default.ExpandMore, contentDescription = null, tint = Color.Gray)
                    }
                }
                DropdownMenu(
                    expanded = showModeDropdown,
                    onDismissRequest = { showModeDropdown = false },
                ) {
                    DropdownMenuItem(
                        text = {
                            Column {
                                Text("All Saved Contacts", fontWeight = FontWeight.SemiBold)
                                Text("Jarvis picks up all contacts (use toggles to block)", fontSize = 12.sp, color = Color.Gray)
                            }
                        },
                        onClick = {
                            filterMode = FilterMode.ALL_SAVED
                            filterManager.setFilterMode(FilterMode.ALL_SAVED)
                            showModeDropdown = false
                        },
                        leadingIcon = { Icon(Icons.Default.People, contentDescription = null) },
                    )
                    DropdownMenuItem(
                        text = {
                            Column {
                                Text("Custom List Only", fontWeight = FontWeight.SemiBold)
                                Text("Jarvis only picks up contacts you enable below", fontSize = 12.sp, color = Color.Gray)
                            }
                        },
                        onClick = {
                            filterMode = FilterMode.CUSTOM
                            filterManager.setFilterMode(FilterMode.CUSTOM)
                            showModeDropdown = false
                        },
                        leadingIcon = { Icon(Icons.Default.FilterList, contentDescription = null) },
                    )
                }
            }

            Spacer(Modifier.height(12.dp))

            // --- Stats Row ---
            val allowedCount = contacts.count { it.isAllowed }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                StatChip(
                    label = "$allowedCount Handled",
                    color = Color(0xFF4CAF50),
                    modifier = Modifier.weight(1f),
                )
                StatChip(
                    label = "${contacts.size - allowedCount} Blocked",
                    color = Color(0xFFE53935),
                    modifier = Modifier.weight(1f),
                )
            }

            Spacer(Modifier.height(12.dp))

            // --- Search ---
            OutlinedTextField(
                value = searchQuery,
                onValueChange = { searchQuery = it },
                placeholder = { Text("Search contacts...", color = Color.Gray) },
                leadingIcon = { Icon(Icons.Default.Search, contentDescription = null, tint = Color.Gray) },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = Color(0xFF6C63FF),
                    unfocusedBorderColor = Color(0xFF2A2A4A),
                    focusedTextColor = Color.White,
                    unfocusedTextColor = Color.White,
                    cursorColor = Color(0xFF6C63FF),
                    focusedContainerColor = Color(0xFF12122A),
                    unfocusedContainerColor = Color(0xFF12122A),
                ),
            )

            Spacer(Modifier.height(8.dp))

            // --- Contact List ---
            Text(
                "CONTACTS  •  ${filteredContacts.size} shown",
                fontSize = 11.sp,
                color = Color.Gray,
                modifier = Modifier.padding(vertical = 4.dp),
            )

            LazyColumn(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                items(filteredContacts, key = { it.number }) { contact ->
                    ContactRow(
                        contact = contact,
                        onToggle = { newValue ->
                            val idx = contacts.indexOfFirst { it.number == contact.number }
                            if (idx >= 0) {
                                contacts = contacts.toMutableList().also { it[idx] = it[idx].copy(isAllowed = newValue) }
                            }
                            if (newValue) filterManager.allowContact(contact.number)
                            else filterManager.blockContact(contact.number)
                        },
                    )
                }
            }

            Spacer(Modifier.height(8.dp))

            // --- Sync Button ---
            if (syncMessage.isNotBlank()) {
                Text(syncMessage, color = Color(0xFF4CAF50), fontSize = 12.sp, modifier = Modifier.padding(bottom = 4.dp))
            }
            Button(
                onClick = {
                    isSyncing = true
                    val savedContacts = phoneAutomator.getSavedContacts()
                    val whitelist = filterManager.buildWhitelist(savedContacts)
                    onSyncContacts(whitelist)
                    syncMessage = "✓ Synced ${whitelist.size} contacts to Jarvis"
                    isSyncing = false
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 16.dp),
                shape = RoundedCornerShape(12.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF6C63FF)),
                enabled = !isSyncing,
            ) {
                if (isSyncing) {
                    CircularProgressIndicator(modifier = Modifier.size(20.dp), color = Color.White, strokeWidth = 2.dp)
                } else {
                    Icon(Icons.Default.CloudUpload, contentDescription = null)
                    Spacer(Modifier.width(8.dp))
                    Text("SYNC TO JARVIS CLOUD", fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

@Composable
private fun ContactRow(contact: ContactItem, onToggle: (Boolean) -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(Color(0xFF12122A))
            .padding(horizontal = 14.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        // Avatar circle with initials
        Box(
            modifier = Modifier
                .size(40.dp)
                .clip(CircleShape)
                .background(if (contact.isAllowed) Color(0xFF1A3A2A) else Color(0xFF2A1A1A)),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = contact.name.take(1).uppercase(),
                color = if (contact.isAllowed) Color(0xFF4CAF50) else Color(0xFFE53935),
                fontWeight = FontWeight.Bold,
                fontSize = 16.sp,
            )
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(
                contact.name,
                color = Color.White,
                fontWeight = FontWeight.SemiBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                contact.number,
                color = Color.Gray,
                fontSize = 12.sp,
            )
        }
        Switch(
            checked = contact.isAllowed,
            onCheckedChange = onToggle,
            colors = SwitchDefaults.colors(
                checkedThumbColor = Color.White,
                checkedTrackColor = Color(0xFF4CAF50),
                uncheckedThumbColor = Color.White,
                uncheckedTrackColor = Color(0xFF444444),
            ),
        )
    }
}

@Composable
private fun StatChip(label: String, color: Color, modifier: Modifier = Modifier) {
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(8.dp))
            .background(color.copy(alpha = 0.15f))
            .padding(horizontal = 12.dp, vertical = 8.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = color, fontWeight = FontWeight.Bold, fontSize = 13.sp)
    }
}
