package com.suhas.globaledgeai.diagnostics

import android.content.Context
import java.io.File
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter

object DiagnosticLog {
    private const val MAX_BYTES = 4_000_000L
    private val fmt = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss.SSS")
    private fun file(context: Context): File = File(context.filesDir, "global-edge-diagnostics.log")

    @Synchronized
    fun log(context: Context, tag: String, message: String, error: Throwable? = null) {
        runCatching {
            val f = file(context)
            if (f.exists() && f.length() > MAX_BYTES) {
                val old = File(context.filesDir, "global-edge-diagnostics.previous.log")
                if (old.exists()) old.delete()
                f.renameTo(old)
            }
            val stamp = ZonedDateTime.now(ZoneId.of("Asia/Kolkata")).format(fmt)
            val safe = message.replace('\n', ' ').replace('\r', ' ').take(1200)
            val err = error?.let { " | ${it::class.java.simpleName}: ${it.message.orEmpty().replace('\n',' ').take(800)}" }.orEmpty()
            f.appendText("$stamp [$tag] $safe$err\n")
        }
    }

    fun snapshot(context: Context): String {
        val header = "Global Edge AI Trader diagnostics\nGenerated: ${ZonedDateTime.now(ZoneId.of("Asia/Kolkata"))}\n\n"
        return header + rawBody(context)
    }

    fun weeklySnapshot(context: Context, learningReport: String): String {
        val now=ZonedDateTime.now(ZoneId.of("Asia/Kolkata"))
        return buildString {
            append("Global Edge AI Trader WEEKLY LEARNING LOG\n")
            append("Generated: $now\n")
            append("Contains autonomous 15-minute audit snapshots and engine diagnostics.\n\n")
            append(learningReport)
            append("\n\n--- DIAGNOSTIC / LEARNING TIMELINE ---\n")
            append(rawBody(context))
        }
    }

    private fun rawBody(context: Context): String {
        val old = File(context.filesDir, "global-edge-diagnostics.previous.log")
        val current = file(context)
        return buildString {
            if (old.exists()) append(old.readText().takeLast(1_500_000))
            if (current.exists()) append(current.readText().takeLast(2_500_000))
        }
    }
}
