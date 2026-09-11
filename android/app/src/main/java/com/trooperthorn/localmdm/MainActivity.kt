package com.trooperthorn.localmdm

import android.app.Activity
import android.os.Bundle
import android.widget.Button
import android.widget.TextView

/** Pairing screen: shows Device Owner state, the address, and the token. */
class MainActivity : Activity() {
    private lateinit var store: PolicyStore
    private lateinit var engine: PolicyEngine

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        store = PolicyStore(this)
        engine = PolicyEngine(this, store)
        MdmService.start(this)
        findViewById<Button>(R.id.rotateToken).setOnClickListener {
            store.rotateToken()
            render()
        }
    }

    override fun onResume() {
        super.onResume()
        render()
    }

    private fun render() {
        findViewById<TextView>(R.id.ownerState).text =
            when (engine.tier) {
                PolicyEngine.TIER_OWNER -> getString(R.string.owner_yes)
                PolicyEngine.TIER_ADMIN -> getString(R.string.tier_admin)
                else -> getString(R.string.owner_no)
            }
        findViewById<TextView>(R.id.address).text =
            "Address: ${Network.localAddress() ?: "no network"}  Port: ${MdmService.PORT}"
        findViewById<TextView>(R.id.token).text = store.token
        findViewById<TextView>(R.id.policySummary).text =
            "Policy v${store.policyVersion}\n${store.policy.toJson().toString(2)}"
    }
}
