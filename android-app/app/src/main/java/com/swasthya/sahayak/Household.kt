package com.swasthya.sahayak

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "households")
data class Household(
    @PrimaryKey val id: String,
    val workerId: String = "",
    val villageCode: String = "",
    val gpsLat: Double = 0.0,
    val gpsLng: Double = 0.0,
    val memberCount: Int = 0
)
