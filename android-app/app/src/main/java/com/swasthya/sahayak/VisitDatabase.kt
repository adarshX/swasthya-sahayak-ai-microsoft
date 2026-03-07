package com.swasthya.sahayak

import android.content.Context
import androidx.room.*

@Dao
interface VisitDao {
    @Insert
    suspend fun insert(record: VisitRecord): Long

    @Query("SELECT * FROM visit_records WHERE synced = 0")
    suspend fun getUnsynced(): List<VisitRecord>

    @Query("UPDATE visit_records SET synced = 1 WHERE id = :id")
    suspend fun markSynced(id: Int)
}

@Database(entities = [VisitRecord::class], version = 1, exportSchema = false)
abstract class VisitDatabase : RoomDatabase() {
    abstract fun visitDao(): VisitDao

    companion object {
        @Volatile private var INSTANCE: VisitDatabase? = null
        fun get(context: Context): VisitDatabase =
            INSTANCE ?: synchronized(this) {
                Room.databaseBuilder(context, VisitDatabase::class.java, "visit_db").build()
                    .also { INSTANCE = it }
            }
    }
}
